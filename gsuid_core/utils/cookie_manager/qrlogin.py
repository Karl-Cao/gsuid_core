import io
import base64
import asyncio
from typing import Any, Tuple, Union, Literal
from pathlib import Path
from http.cookies import SimpleCookie

import aiofiles

from gsuid_core.bot import Bot
from gsuid_core.i18n import t
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.api.mys_api import mys_api
from gsuid_core.utils.cookie_manager.verified_game_uid import owns_game_uid


async def get_qrcode_base64(url: str, path: Path, bot_id: str) -> bytes:
    # qrcode(+约2.7MB, 连带 PIL) 仅扫码登录时用到, 按需导入避免常驻启动内存。
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L
    from qrcode.image.pil import PilImage

    qr = qrcode.QRCode(  # type: ignore
        version=1,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(255, 134, 36), back_color="white")
    assert isinstance(img, PilImage)

    if bot_id == "onebot":
        img = img.resize((700, 700))  # type: ignore
        img.save(  # type: ignore
            path,
            format="PNG",
            save_all=True,
            append_images=[img],
            duration=100,
            loop=0,
        )
        async with aiofiles.open(path, "rb") as fp:
            img = await fp.read()
    elif bot_id == "onebot_v12":
        img_byte = io.BytesIO()
        img.save(img_byte, format="PNG")  # type: ignore
        img_byte = img_byte.getvalue()
        img = f"base64://{base64.b64encode(img_byte).decode()}"
        return img  # type: ignore
    else:
        img_byte = io.BytesIO()
        img.save(img_byte, format="PNG")  # type: ignore
        img = img_byte.getvalue()

    return img


async def refresh(
    code_data: dict,
) -> Union[Tuple[Literal[False], None], Tuple[Literal[True], Any]]:
    scanned = False
    while True:
        await asyncio.sleep(2)
        status_data = await mys_api.check_hyp_qrcode(
            code_data["ticket"],
            code_data["device_id"],
        )
        if isinstance(status_data, int):
            logger.warning(t("log.cookie.login_qr_code_expired"))
            return False, None
        if status_data["status"] == "Created":
            continue
        if status_data["status"] == "Scanned":
            if not scanned:
                logger.info(t("log.cookie.login_qr_code_scanned"))
                scanned = True
            continue
        if status_data["status"] == "Confirmed":
            logger.info(t("log.cookie.login_qr_code_confirmed"))
            break
        logger.warning(t("log.cookie.login_qr_code_status", p0=status_data["status"]))
        return False, None
    return True, status_data


async def qrcode_login(
    bot: Bot,
    ev: Event,
    user_id: str,
    expected_uid: str | None = None,
    expected_game_id: str = "8",
) -> str:
    game_name = "原神" if expected_game_id == "2" else "绝区零"

    async def send_msg(msg: str):
        if expected_uid is not None:
            await bot.send(MessageSegment.markdown(f'<qqbot-at-user id="{ev.user_id}" /> {msg}'))
        else:
            await bot.send(msg)
        return ""

    code_data = await mys_api.create_hyp_qrcode_url()
    if isinstance(code_data, int):
        return await send_msg("[登录]链接创建失败...")

    path = Path(__file__).parent / f"{user_id}.gif"

    qr_image = await get_qrcode_base64(code_data["url"], path, ev.bot_id)
    im = []
    if expected_uid is not None:
        im.append(
            MessageSegment.text(
                "请本人使用米游社扫描下方二维码。群内所有成员都能看见它，请勿代扫；"
                f"扫码账号的{game_name} UID 必须与发起人已绑定的 UID 相同，否则不会保存凭据。"
            )
        )
    else:
        im.append(MessageSegment.text("请使用米游社扫描下方二维码登录："))
    im.append(MessageSegment.image(qr_image))
    im.append(
        MessageSegment.text(
            "免责声明:您将通过扫码完成获取米游社sk以及ck。\n"
            "我方仅提供米游社查询及相关游戏内容服务,\n"
            "若您的账号封禁、被盗等处罚与我方无关。\n"
            "害怕风险请勿扫码~"
        )
    )
    if expected_uid is not None:
        # Keep the verified image reply and separate real QQ markdown mention.
        # The image reply also identifies its requester by visible nickname.
        await bot.send(im)
        bot.ev.msg_id = ""  # Post-scan status is a new group message.
    else:
        await bot.send(MessageSegment.node(im))

    if path.exists():
        path.unlink()

    status, login_data = await refresh(code_data)
    return await _finish_qrcode_login(bot, ev, user_id, expected_uid, status, login_data, expected_game_id)


async def _finish_qrcode_login(
    bot: Bot,
    ev: Event,
    user_id: str,
    expected_uid: str | None,
    status: bool,
    login_data: Any,
    expected_game_id: str = "8",
) -> str:
    game_name = "原神" if expected_game_id == "2" else "绝区零"

    async def send_msg(msg: str):
        if expected_uid is not None:
            await bot.send(MessageSegment.markdown(f'<qqbot-at-user id="{ev.user_id}" /> {msg}'))
        else:
            await bot.send(msg)
        return ""

    if status:
        assert login_data is not None  # 骗过 pyright
        tokens = login_data.get("tokens", [])
        user_info = login_data.get("user_info") or {}
        if not tokens or "mid" not in user_info:
            return await send_msg("[登录]获取SK失败...")

        account_id = str(user_info.get("aid") or user_info.get("uid") or user_info.get("account_id", ""))
        if not account_id:
            return await send_msg("[登录]获取account_id失败...")

        stoken = ""
        for token in tokens:
            if token.get("name") in {"stoken", "stoken_v2"}:
                stoken = token["token"]
                break
        if not stoken:
            stoken = tokens[0]["token"]
        mid = user_info["mid"]
        app_cookie = f"stuid={account_id};stoken={stoken};mid={mid}"
        logger.info(t("log.cookie.stoken_ok"))

        ck = await mys_api.get_cookie_token_by_stoken(stoken, account_id, app_cookie)
        if isinstance(ck, int):
            return await send_msg("[登录]获取CK失败...")

        if expected_uid is not None:
            # A group QR is visible to everyone. Never persist the scanned account
            # unless it actually owns the command sender's bound ZZZ game UID.
            account_cookie = f"account_id={account_id};cookie_token={ck['cookie_token']}"
            try:
                roles = await mys_api.get_mihoyo_bbs_info(account_id, account_cookie)
            except Exception:
                logger.warning(t("log.cookie.stoken_fail"))
                return await send_msg(f"[登录]无法核对扫码账号的{game_name}UID，凭据未保存。请稍后重试。")
            if not isinstance(roles, list):
                return await send_msg(f"[登录]无法核对扫码账号的{game_name}UID，凭据未保存。请稍后重试。")
            if not owns_game_uid(roles, expected_uid, expected_game_id):
                return await send_msg(f"[登录]扫码账号与发起人的{game_name}UID不符，凭据未保存。请本人重新扫码。")

        return SimpleCookie(
            {
                "stoken_v2": stoken,
                "stuid": account_id,
                "mid": mid,
                "cookie_token": ck["cookie_token"],
            }
        ).output(header="", sep=";")
    else:
        logger.warning(t("log.cookie.stoken_fail"))
        im = "[登录]stoken获取失败: 二维码已过期"

    return await send_msg(im)
