import asyncio
import logging
from typing import Optional
from livekit import rtc
from livekit.agents import stt, utils
import google.generativeai as genai
import os
import io

logger = logging.getLogger(__name__)


class GeminiSTT(stt.STT):
    """
    Custom Speech-to-Text implementation using Gemini Flash 2.5 API directly.
    This bypasses Google Cloud and uses the Gemini API for transcription.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash-exp",
        language: str = "en-US",
        sample_rate: int = 16000,
    ):
        """
        Initialize Gemini STT.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Gemini model to use for transcription
            language: Language code for transcription
            sample_rate: Audio sample rate in Hz
        """
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY must be set in environment or provided as parameter")
        
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        
        # Configure Gemini
        genai.configure(api_key=self._api_key)
        logger.info(f"Initialized GeminiSTT with model: {model}")

    async def _recognize_impl(
        self, 
        buffer: utils.AudioBuffer, 
        *, 
        language: Optional[str] = None
    ) -> stt.SpeechEvent:
        """
        Recognize speech from an audio buffer using Gemini API.
        
        Args:
            buffer: Audio buffer containing speech data
            language: Language code (optional override)
            
        Returns:
            SpeechEvent with transcription results
        """
        target_language = language or self._language
        
        try:
            # Convert audio buffer to WAV format
            audio_data = self._audio_buffer_to_wav(buffer)
            
            # Upload audio to Gemini
            logger.debug(f"Uploading audio to Gemini (size: {len(audio_data)} bytes)")
            audio_file = genai.upload_file(
                io.BytesIO(audio_data),
                mime_type="audio/wav"
            )
            
            # Use Gemini to transcribe
            model = genai.GenerativeModel(self._model)
            
            prompt = f"Transcribe this audio to text in {target_language}. Only return the transcription without any additional commentary."
            
            logger.debug(f"Requesting transcription from {self._model}")
            response = await asyncio.to_thread(
                model.generate_content,
                [prompt, audio_file]
            )
            
            # Extract transcription
            transcription = response.text.strip() if response.text else ""
            
            # Clean up uploaded file
            try:
                await asyncio.to_thread(genai.delete_file, audio_file.name)
            except Exception as e:
                logger.warning(f"Failed to delete uploaded file: {e}")
            
            logger.info(f"Transcription result: {transcription}")
            
            # Create final speech event
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text=transcription,
                        language=target_language,
                    )
                ],
            )
            
        except Exception as e:
            logger.error(f"Gemini STT error: {e}", exc_info=True)
            # Return empty result on error
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text="",
                        language=target_language,
                    )
                ],
            )

    def _audio_buffer_to_wav(self, buffer: utils.AudioBuffer) -> bytes:
        """
        Convert AudioBuffer to WAV format bytes.
        
        Args:
            buffer: Audio buffer to convert
            
        Returns:
            WAV file as bytes
        """
        import wave
        import numpy as np
        
        # Get audio data as numpy array
        audio_data = buffer.data
        
        # Convert to 16-bit PCM
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(buffer.num_channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(buffer.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        return wav_buffer.getvalue()

    async def aclose(self) -> None:
        """Close the STT instance and cleanup resources."""
        logger.info("Closing GeminiSTT")
        await super().aclose()
