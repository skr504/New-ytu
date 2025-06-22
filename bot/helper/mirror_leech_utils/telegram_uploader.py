from utils.meta_config import get_meta_settings, is_metadata_enabled  # Add this at top

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

    # ✅ Inject metadata if enabled
    if is_metadata_enabled():
        cap_mono += f"\n\n🔖 Uploaded by: {get_meta_settings()}"

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
                    self._listener.screen
