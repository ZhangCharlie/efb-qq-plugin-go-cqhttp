import base64
import html
import json
import logging
import sys

import magic
from ehforwarderbot import Chat, Message, MsgType
from ehforwarderbot.message import LinkAttribute, LocationAttribute, Substitutions

from . import GoCQHttp
from .Utils import cq_get_image, download_file, download_voice


class QQMsgProcessor:
    inst: GoCQHttp
    logger: logging.Logger = logging.getLogger(__name__)

    def __init__(self, instance: GoCQHttp):
        self.inst = instance
        self._ = instance._
        pass

    def qq_image_wrapper(self, data, chat: Chat = None):
        efb_msg = Message()
        if "url" not in data:
            efb_msg.type = MsgType.Text
            efb_msg.text = self._("[Image Source missing]")
            return [efb_msg]

        efb_msg.file = cq_get_image(data["url"])
        if efb_msg.file is None:
            efb_msg.type = MsgType.Text
            efb_msg.text = self._("[Download image failed, please check on your QQ client]")
            return [efb_msg]

        efb_msg.type = MsgType.Image
        mime = magic.from_file(efb_msg.file.name, mime=True)
        if isinstance(mime, bytes):
            mime = mime.decode()
        efb_msg.filename = data["file"] if "file" in data else efb_msg.file.name
        efb_msg.filename += "." + str(mime).split("/")[1]
        efb_msg.path = efb_msg.file.name
        efb_msg.mime = mime
        if "gif" in mime:
            efb_msg.type = MsgType.Animation
        return [efb_msg]

    def qq_record_wrapper(self, data, chat: Chat = None):  # Experimental!
        efb_msg = Message()
        try:
            transformed_file = self.inst.coolq_api_query("get_record", file=data["file"], out_format="mp3")
            efb_msg.type = MsgType.Audio
            efb_msg.file = download_voice(
                transformed_file["file"],
                self.inst.client_config["api_root"].rstrip("/"),
                self.inst.client_config["access_token"],
            )
            mime = magic.from_file(efb_msg.file.name, mime=True)
            if isinstance(mime, bytes):
                mime = mime.decode()
            efb_msg.path = efb_msg.file.name
            efb_msg.mime = mime
        except Exception:
            efb_msg.type = MsgType.Unsupported
            efb_msg.text = self._("[Voice Message] Please check it on your QQ")
            logging.getLogger(__name__).exception("Failed to download voice")
        return [efb_msg]

    def qq_share_wrapper(self, data, chat: Chat = None):
        efb_msg = Message(
            type=MsgType.Link,
            text="",
            attributes=LinkAttribute(
                title="" if "title" not in data else data["title"],
                description="" if "content" not in data else data["content"],
                image="" if "image" not in data else data["image"],
                url=data["url"],
            ),
        )
        return [efb_msg]

    def qq_location_wrapper(self, data, chat: Chat = None):
        efb_msg = Message(
            text=data["content"],
            type=MsgType.Location,
            attributes=LocationAttribute(longitude=float(data["lon"]), latitude=float(data["lat"])),
        )
        return [efb_msg]

    def qq_shake_wrapper(self, data, chat: Chat = None):
        efb_msg = Message(type=MsgType.Text, text=self._("[Your friend shakes you!]"))
        return [efb_msg]

    def qq_contact_wrapper(self, data, chat: Chat = None):
        uid = data["id"]
        contact_type = data["type"]
        efb_msg = Message(
            type=MsgType.Text,
            text=self._("Chat Recommendation Received\nID: {}\nType: {}").format(uid, contact_type),
        )
        return [efb_msg]

    def qq_bface_wrapper(self, data, chat: Chat = None):
        efb_msg = Message(
            type=MsgType.Unsupported,
            text=self._("[Here comes the BigFace Emoji, please check it on your phone]"),
        )
        return [efb_msg]

    def qq_small_face_wrapper(self, data, chat: Chat = None):
        # todo this function's maybe not necessary?
        pass

    def qq_sign_wrapper(self, data, chat: Chat = None):
        location = self._("at {}").format(data["location"]) if "location" in data else self._("at Unknown Place")
        title = "" if "title" not in data else (self._("with title {}").format(data["title"]))
        efb_msg = Message(
            type=MsgType.Text,
            text=self._("signed in {location} {title}").format(title=title, location=location),
        )
        return [efb_msg]

    def qq_rich_wrapper(self, data: dict, chat: Chat = None):  # Buggy, Help needed
        efb_messages = list()
        efb_msg = Message(
            type=MsgType.Unsupported,
            text=self._("[Here comes the Rich Text, dumping...] \n"),
        )
        for key, value in data.items():
            efb_msg.text += key + ": " + value + "\n"
        efb_messages.append(efb_msg)
        # Optimizations for rich messages
        # Group Broadcast
        _ = self.qq_group_broadcast_wrapper(data, chat)
        if _ is not None:
            efb_messages.append(_)

        return efb_messages

    def qq_music_wrapper(self, data, chat: Chat = None):
        efb_msg = Message()
        if data["type"] == "163":  # Netease Cloud Music
            efb_msg.type = MsgType.Text
            efb_msg.text = "https://music.163.com/#/song?id=" + data["id"]
        else:
            efb_msg.type = MsgType.Text
            efb_msg.text = data["text"]
        return [efb_msg]  # todo Port for other music platform

    def qq_text_simple_wrapper(self, text: str, ats: dict):  # This cute function only accepts string!
        efb_msg = Message()
        efb_msg.type = MsgType.Text
        efb_msg.text = text
        if ats:  # This is used to replace specific text with @blahblah
            # And Milkice really requires a brain check
            efb_msg.substitutions = Substitutions(ats)
        return efb_msg

    def coolq_code_at_wrapper(self, uid):
        return "[CQ:at,qq={}]".format(uid)

    def coolq_code_image_wrapper(self, file, file_path):
        if file.closed:
            file = open(file.name)
        encoded_string = base64.b64encode(file.read())
        # Since base64 doesn't contain characters which isn't allowed in CQ Code,
        # there's no need to escape the special characters
        return "[CQ:image,file=base64://{}]".format(encoded_string.decode())

    def coolq_voice_image_wrapper(self, file, file_path):
        if file.closed:
            file = open(file.name)
        encoded_string = base64.b64encode(file.read())
        # Since base64 doesn't contain characters which isn't allowed in CQ Code,
        # there's no need to escape the special characters
        return "[CQ:record,file=base64://{}]".format(encoded_string.decode())

    def qq_file_after_wrapper(self, data):
        efb_msg = Message()
        efb_msg.file = data["file"]
        efb_msg.type = MsgType.File
        mime = magic.from_file(efb_msg.file.name, mime=True)
        if isinstance(mime, bytes):
            mime = mime.decode()
        efb_msg.path = efb_msg.file.name
        efb_msg.mime = mime
        efb_msg.filename = data["filename"]
        return efb_msg

    def qq_group_broadcast_wrapper(self, data, chat: Chat = None):
        try:
            at_list = {}
            content_data = json.loads(data["content"])
            text_data = base64.b64decode(content_data["mannounce"]["text"]).decode("UTF-8")
            title_data = base64.b64decode(content_data["mannounce"]["title"]).decode("UTF-8")
            text = "［群公告］ 【{title}】\n{text}".format(title=title_data, text=text_data)

            substitution_begin = len(text) + 1
            substitution_end = len(text) + len("@all") + 2
            text += " @all "

            at_list[(substitution_begin, substitution_end)] = chat.self

            if "pic" in content_data["mannounce"]:  # Picture Attached
                # Assuming there's only one picture
                data["url"] = "http://gdynamic.qpic.cn/gdynamic/{}/628".format(
                    content_data["mannounce"]["pic"][0]["url"]
                )
                efb_message = self.qq_image_wrapper(data)[0]
                efb_message.text = text
                efb_message.substitutions = Substitutions(at_list)
                return [efb_message]
            else:
                return self.qq_text_simple_wrapper(text, at_list)
        except Exception:
            return self.qq_group_broadcast_alternative_wrapper(data)

    def qq_group_broadcast_alternative_wrapper(self, data, chat: Chat = None):
        try:
            at_list = {}
            content_data = json.loads(data["content"])
            group_id = content_data["mannounce"]["gc"]
            notice_raw_data = self.inst.coolq_api_query("_get_group_notice", group_id=group_id)
            notice_data = json.loads(notice_raw_data)
            title_data = html.unescape(notice_data[0]["msg"]["title"])
            text_data = html.unescape(notice_data[0]["msg"]["text"])
            text = "［群公告］ 【{title}】\n{text}".format(title=title_data, text=text_data)

            substitution_begin = len(text) + 1
            substitution_end = len(text) + len("@all") + 2
            text += " @all "

            at_list[(substitution_begin, substitution_end)] = chat.self

            if "pics" in html.unescape(notice_data[0]["msg"]):  # Picture Attached
                # Assuming there's only one picture
                data["url"] = "http://gdynamic.qpic.cn/gdynamic/{}/628".format(notice_data[0]["msg"]["pics"][0]["id"])
                efb_message = self.qq_image_wrapper(data)[0]
                efb_message.text = text
                efb_message.substitutions = Substitutions(at_list)
                return [efb_message]
            else:
                return self.qq_text_simple_wrapper(text, at_list)
        except Exception:
            return None

    def qq_xml_wrapper(self, data, chat: Chat = None):
        efb_msg = Message()
        efb_msg.type = MsgType.Text
        efb_msg.text = data["data"]
        return [efb_msg]

    def qq_json_wrapper(self, data, chat: Chat = None):
        efb_msg = Message()
        efb_msg.type = MsgType.Text
        efb_msg.text = data["data"]

        try:
            # In general, data['data'] is a JSON string
            dict_data = json.loads(efb_msg.text)
            if type(dict_data) != dict or "app" not in dict_data:
                return [efb_msg]

            # Group of announcement
            if dict_data["app"] == "com.tencent.mannounce":
                meta_mannounce = dict_data["meta"]["mannounce"]
                efb_msg.text = "[{prompt}]\n\n{text}".format(
                    prompt=str(base64.b64decode(meta_mannounce["title"]), "UTF-8"),
                    text=str(base64.b64decode(meta_mannounce["text"]), "UTF-8"),
                )

            # Watch, listen and play together
            elif dict_data["app"] == "com.tencent.together":
                meta_invite = dict_data["meta"]["invite"]
                efb_msg.text = "[{prompt}]\n\n{text}\n\n{cover}".format(
                    prompt=meta_invite["title"],
                    text=meta_invite["summary"],
                    cover=meta_invite["cover"],
                )

            # QQ vip card
            elif dict_data["app"] == "com.tencent.qqvip_singlepic":
                efb_msg.text = efb_msg.text

            # Tencent mini App (01 unknown)
            elif dict_data["app"] == "com.tencent.miniapp_01":
                meta_detail1 = dict_data["meta"]["detail_1"]
                url = meta_detail1["qqdocurl"] if "qqdocurl" in meta_detail1 else meta_detail1["url"]
                efb_msg.text = "{prompt}\n\n{desc}\n\n{url}\n\n{preview}".format(
                    prompt=dict_data["prompt"],
                    desc=meta_detail1["desc"],
                    url=url,
                    preview=meta_detail1["preview"],
                )

            # Shared third-party Apps
            elif dict_data["app"] == "com.tencent.structmsg":
                meta_view = dict_data["meta"][dict_data["view"]]
                efb_msg.text = "{prompt}\n\n{desc}\n\n{url}\n\n{preview}".format(
                    prompt=dict_data["prompt"],
                    desc=meta_view["desc"],
                    url=meta_view["jumpUrl"],
                    preview=meta_view["preview"],
                )

        except Exception:
            self.logger.error(f"json_wrapper_info: {data}\nexc_info:{sys.exc_info()[0]}")

        return [efb_msg]

    def qq_video_wrapper(self, data, chat: Chat = None):
        res = download_file(data["url"])
        mime = magic.from_file(res.name, mime=True)
        if isinstance(mime, bytes):
            mime = mime.decode()
        efb_msg = Message(type=MsgType.Video, file=res, filename=res.name, mime=mime)
        return [efb_msg]

    def qq_unsupported_wrapper(self, data, chat: Chat = None):
        efb_msg = Message(type=MsgType.Unsupported, text=data)
        return [efb_msg]
