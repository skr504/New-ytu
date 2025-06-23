from utils.meta_config import get_meta_settings, is_metadata_enabled
from PIL import Image
from os import path as ospath, remove
from asyncio import sleep
from re import match as re_match
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from pyrogram.errors import FloodWait, FloodPremiumWait, BadRequest, RPCError

@retry(
    wait=wait_exponential(multiplier=2, min=4, max=8),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
)
async def _upload_file(self, cap_mono, file, o_path, force_document=False):
    if (
        self._thumb is not None
        and not await aiopath.exists(self._thumb)
        and self._thumb != "none"
    ):
        self._thumb = None

    thumb = self._thumb
    self._is_corrupted = False

    # ✅ Add metadata to caption if enabled
    from_user_id = self._listener.user_id if hasattr(self._listener, "user_id") else None
    meta_enabled, meta_text = get_meta_settings(from_user_id) if from_user_id else (False, None)

    if meta_enabled and meta_text:
        cap_mono += f"\n\n{meta_text}"

    try:
        is_video, is_audio, is_image = await get_document_type(self._up_path)

        if not is_image and thumb is None:
            file_name = ospath.splitext(file)[0]
            thumb_path = f"{self._path}/yt-dlp-thumb/{file_name}.jpg"
            if await aiopath.isfile(thumb_path):
                thumb = thumb_path
            elif is_audio and not is_video:
                thumb = await get_audio_thumbnail(self._up_path)

        if (
            self._listener.as_doc
            or force_document
            or (not is_video and not is_audio and not is_image)
        ):
            key = "documents"
            if is_video and thumb is None:
                thumb = await get_video_thumbnail(self._up_path, None)

            if self._listener.is_cancelled:
                return
            if thumb == "none":
                thumb = None

            self._sent_msg = await self._sent_msg.reply_document(
                document=self._up_path,
                quote=True,
                thumb=thumb,
                caption=cap_mono,
                force_document=True,
                disable_notification=True,
                progress=self._upload_progress,
            )

        elif is_video:
            key = "videos"
            duration = (await get_media_info(self._up_path))[0]
            if thumb is None and self._listener.thumbnail_layout:
                thumb = await get_multiple_frames_thumbnail(
                    self._up_path,
                    self._listener.thumbnail_layout,
                    self._listener.screen_shots,
                )
            if thumb is None:
                thumb = await get_video_thumbnail(self._up_path, duration)
            if thumb is not None and thumb != "none":
                with Image.open(thumb) as img:
                    width, height = img.size
            else:
                width = 480
                height = 320
            if self._listener.is_cancelled:
                return
            if thumb == "none":
                thumb = None

            self._sent_msg = await self._sent_msg.reply_video(
                video=self._up_path,
                quote=True,
                caption=cap_mono,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb,
                supports_streaming=True,
                disable_notification=True,
                progress=self._upload_progress,
            )

        elif is_audio:
            key = "audios"
            duration, artist, title = await get_media_info(self._up_path)
            if self._listener.is_cancelled:
                return
            if thumb == "none":
                thumb = None

            self._sent_msg = await self._sent_msg.reply_audio(
                audio=self._up_path,
                quote=True,
                caption=cap_mono,
                duration=duration,
                performer=artist,
                title=title,
                thumb=thumb,
                disable_notification=True,
                progress=self._upload_progress,
            )

        else:
            key = "photos"
            if self._listener.is_cancelled:
                return

            self._sent_msg = await self._sent_msg.reply_photo(
                photo=self._up_path,
                quote=True,
                caption=cap_mono,
                disable_notification=True,
                progress=self._upload_progress,
            )

        # ✅ Handle media group
        if (
            not self._listener.is_cancelled
            and self._media_group
            and (self._sent_msg.video or self._sent_msg.document)
        ):
            key = "documents" if self._sent_msg.document else "videos"
            if match := re_match(r".+(?=\.0*\d+$)|.+(?=\.part\d+\..+$)", o_path):
                pname = match.group(0)
                if pname in self._media_dict[key]:
                    self._media_dict[key][pname].append(
                        [self._sent_msg.chat.id, self._sent_msg.id]
                    )
                else:
                    self._media_dict[key][pname] = [
                        [self._sent_msg.chat.id, self._sent_msg.id]
                    ]
                msgs = self._media_dict[key][pname]
                if len(msgs) == 10:
                    await self._send_media_group(pname, key, msgs)
                else:
                    self._last_msg_in_group = True

        if self._thumb is None and thumb and await aiopath.exists(thumb):
            await remove(thumb)

    except (FloodWait, FloodPremiumWait) as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.3)
        if self._thumb is None and thumb and await aiopath.exists(thumb):
            await remove(thumb)
        return await self._upload_file(cap_mono, file, o_path)

    except Exception as err:
        if self._thumb is None and thumb and await aiopath.exists(thumb):
            await remove(thumb)
        err_type = "RPCError: " if isinstance(err, RPCError) else ""
        LOGGER.error(f"{err_type}{err}. Path: {self._up_path}")
        if isinstance(err, BadRequest) and key != "documents":
            LOGGER.error(f"Retrying As Document. Path: {self._up_path}")
            return await self._upload_file(cap_mono, file, o_path, True)
        raise err
