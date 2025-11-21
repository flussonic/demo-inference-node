#!/usr/bin/env python3

from capture import Capture, Episode
from episodes_server import run_http
import threading
import cv2
import datetime as dt
import os

from manager import Manager

detector = cv2.QRCodeDetector()
qr_codes = {}


class QrRecognizer(Capture):
	def __init__(self, spec):
		super().__init__(spec)
		self.started = False
		# Track active QR code episodes: {qr_data: episode_id}
		# This allows us to update existing episodes and close them when QR disappears
		self.active_qr_episodes = {}

	def preprocess_image(self, image):
		"""Preprocess image to improve QR code detection"""
		# Convert to grayscale if needed
		if len(image.shape) == 3:
			gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
		else:
			gray = image
		
		# Apply adaptive thresholding to improve contrast
		# This helps with QR codes in varying lighting conditions
		adaptive = cv2.adaptiveThreshold(
			gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
			cv2.THRESH_BINARY, 11, 2
		)
		
		return gray, adaptive

	def process(self, image, utc_ns):
		timestamp = dt.datetime.fromtimestamp(utc_ns/1e9, tz=dt.UTC)
		if not self.started:
			print(f"[{self.name}] First frame arrived on {timestamp}, image shape: {image.shape}")
			self.started = True

		gray, adaptive = self.preprocess_image(image)
		retval, decoded_info, points, _ = detector.detectAndDecodeMulti(image)

		if hasattr(self, '_qr_check_count'):
			self._qr_check_count += 1
		else:
			self._qr_check_count = 1

		if self._qr_check_count % 100 == 0:
			print(f"[{self.name}] QR detection attempt #{self._qr_check_count}, retval={retval}, decoded_info count={len(decoded_info) if decoded_info else 0}")
		if not retval or not decoded_info or len(decoded_info) == 0:
			retval, decoded_info, points, _ = detector.detectAndDecodeMulti(gray)

		if not retval or not decoded_info or len(decoded_info) == 0:
			retval, decoded_info, points, _ = detector.detectAndDecodeMulti(adaptive)

		current_frame_qr_codes = set()
		if retval and decoded_info:
			valid_qr_codes = [qr for qr in decoded_info if qr and qr.strip()]
			if valid_qr_codes:
				print(f"[{self.name}] Found {len(valid_qr_codes)} QR code(s): {valid_qr_codes}")
			for qr_data in valid_qr_codes:
				current_frame_qr_codes.add(qr_data)

				if qr_data in self.active_qr_episodes:
					# QR code already has an active episode - update it
					episode_id = self.active_qr_episodes[qr_data]
					updated_episode = Capture.update_episode(
						episode_id,
						updated_at=int(utc_ns/1e6)
					)
					if updated_episode:
						print(f"[{self.name}] Updated episode for QR: {qr_data} (episode_id: {episode_id})")
				else:
					# New QR code detected - create new episode
					episode_id = int(utc_ns/1e3)
					self.active_qr_episodes[qr_data] = episode_id
					qr_codes[qr_data] = (qr_data, timestamp)
					print(f"[{self.name}] NEW QR CODE DETECTED: {qr_data} at {timestamp} (episode_id: {episode_id})")
					return Episode(
						episode_id=episode_id,
						media=self.name,
						opened_at=int(utc_ns/1e6),
						started_at=int(utc_ns/1e6),  # started_at = opened_at
						updated_at=int(utc_ns/1e6),
						episode_type=Episode.QR_CODE,
						payload={'qr_url': qr_data}
					)

		disappeared_qr_codes = set(self.active_qr_episodes.keys()) - current_frame_qr_codes
		if disappeared_qr_codes:
			for qr_data in disappeared_qr_codes:
				episode_id = self.active_qr_episodes[qr_data]
				# Close the episode
				closed_episode = Capture.update_episode(
					episode_id,
					closed_at=int(utc_ns/1e6),
					updated_at=int(utc_ns/1e6)
				)
				if closed_episode:
					print(f"[{self.name}] QR CODE DISAPPEARED: {qr_data} at {timestamp}, closed episode {episode_id}")
				# Remove from active episodes
				del self.active_qr_episodes[qr_data]

		return None

class MyManager(Manager):
	def __init__(self, url):
		super().__init__(url)

	def launch(self, spec):
		return QrRecognizer(spec)


manager = MyManager(os.environ['CONFIG_EXTERNAL'])
t1 = threading.Thread(target=manager.run, args=())
t1.start()
run_http(Capture.episodes, 8020, manager=manager)
