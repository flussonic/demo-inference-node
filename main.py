#!/usr/bin/env python3

from capture import Capture, Episode
from episodes_server import run_http
import threading
import cv2
import datetime as dt
import sys

detector = cv2.QRCodeDetector()
qr_codes = {}


class QrRecognizer(Capture):
	def __init__(self, rtsp_url):
		super().__init__(rtsp_url)
		self.started = False

	def process(self, image, utc_ns):
		timestamp = dt.datetime.fromtimestamp(utc_ns/1e9, tz=dt.UTC)
		if not self.started:
			print("Started on", timestamp)
			self.started = True

		data, bbox, _ = detector.detectAndDecode(image)
		if data and data not in qr_codes:
			qr_codes[data] = (data, timestamp)
			print("%s\n%s\n\n" % (timestamp,data))
			return Episode(
				episode_id=int(utc_ns/1e3),
				media="cam1",
				opened_at=int(utc_ns/1e6),
				updated_at=int(utc_ns/1e6),
				payload=data
			)


capture = QrRecognizer(sys.argv[1])


t1 = threading.Thread(target=capture.run, args=())
t1.start()

run_http(Capture.episodes, 8000)