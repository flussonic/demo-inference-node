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
		# Track active QR codes: {qr_data: {'opened_at': timestamp_ms, 'first_seen_at': timestamp_ms}}
		# Episodes are created only when QR code disappears
		self.active_qr_codes = {}

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

		# Log QR detection attempts more frequently for debugging
		if self._qr_check_count == 1:
			print(f"[{self.name}] Starting QR code detection, image shape: {image.shape}")
		elif self._qr_check_count % 30 == 0:
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

				if qr_data not in self.active_qr_codes:
					# New QR code detected - track it but don't create episode yet
					opened_at_ms = int(utc_ns/1e6)
					self.active_qr_codes[qr_data] = {
						'opened_at': opened_at_ms,
						'first_seen_at': opened_at_ms
					}
					qr_codes[qr_data] = (qr_data, timestamp)
					print(f"[{self.name}] NEW QR CODE DETECTED: {qr_data} at {timestamp}")

		# Check for disappeared QR codes - create episodes when they disappear
		disappeared_qr_codes = set(self.active_qr_codes.keys()) - current_frame_qr_codes
		if disappeared_qr_codes:
			for qr_data in disappeared_qr_codes:
				qr_info = self.active_qr_codes[qr_data]
				opened_at_ms = qr_info['opened_at']
				closed_at_ms = int(utc_ns/1e6)
				episode_id = int(utc_ns/1e3)
				
				# Create episode when QR code disappears
				episode = Episode(
					episode_id=episode_id,
					media=self.name,
					opened_at=opened_at_ms,
					started_at=opened_at_ms,  # started_at = opened_at
					closed_at=closed_at_ms,
					updated_at=closed_at_ms,
					episode_type=Episode.QR_CODE,
					payload={'qr_url': qr_data}
				)
				print(f"[{self.name}] QR CODE DISAPPEARED: {qr_data} at {timestamp}, created episode {episode_id} (opened: {opened_at_ms}, closed: {closed_at_ms})")
				
				# Remove from active QR codes
				del self.active_qr_codes[qr_data]
				
				return episode

		return None

class MyManager(Manager):
	def __init__(self, url):
		super().__init__(url)

	def launch(self, spec):
		return QrRecognizer(spec)


print("[Main] Starting inference node...")
config_external = os.environ.get('CONFIG_EXTERNAL')
if not config_external:
	print("[Main] ERROR: CONFIG_EXTERNAL environment variable is not set!")
	exit(1)
print(f"[Main] CONFIG_EXTERNAL: {config_external}")

manager = MyManager(config_external)
print("[Main] Manager created, starting manager thread...")
t1 = threading.Thread(target=manager.run, args=())
t1.start()
print("[Main] Manager thread started, starting HTTP server on port 8020...")
run_http(Capture.episodes, 8020, manager=manager)
