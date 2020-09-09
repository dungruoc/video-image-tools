#!/usr/bin/env python3

import cv2
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject
import argparse

from datetime import datetime
import os

class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

    def init(self, cap, resolution, fps = 30):
        self.cap = cap
        self.cap_shape = resolution
        self.number_frames = 0
        self.duration = 1 / fps * Gst.SECOND  # duration of a frame in nanoseconds
        caps_str = 'caps=video/x-raw,format=BGR,width={},height={},framerate={}/1 '.format(self.cap_shape[1],
                                                                                       self.cap_shape[0],
                                                                                       fps)
        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' + \
                             caps_str + \
                             '! videoconvert ! video/x-raw,format=I420 ' + \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' + \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'
        print(self.launch_string)

        self.detector = MinerTopDectector(window_size=5, threshold=0.25, stablizer_size=3, equalizer_in=False, equalizer_out=True, blogging=False)

    def on_need_data(self, src, lenght):
        if self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                if frame.shape[:2] != self.cap_shape:
                    print(frame.shape[:2], ' vs ', self.cap_shape)
                    frame = cv2.resize(frame, self.cap_shape, interpolation=cv2.INTER_AREA)
                data = frame.tostring()
                buf = Gst.Buffer.new_allocate(None, len(data), None)
                buf.fill(0, data)
                buf.duration = self.duration # Gst.CLOCK_TIME_NONE 
                timestamp = self.number_frames * self.duration
                buf.pts = buf.dts = int(timestamp)
                buf.offset = timestamp
                self.number_frames += 1
                retval = src.emit('push-buffer', buf)
                if retval != Gst.FlowReturn.OK:
                    print(retval)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        self.appsrc = rtsp_media.get_element().get_child_by_name('source')
        self.appsrc.connect('need-data', self.on_need_data)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)

    @staticmethod
    def _resolution(video_cap):
        if video_cap.isOpened():
            ret, frame = video_cap.read()
            if ret:
                return frame.shape[:2]
        return (480, 640)

    def start(self, input_stream = 0, host = '0.0.0.0', port = '8554', uri = ""):
        print(input_stream, host, port, uri)
        fps = 30
        if input_stream[:7].lower() == 'rtsp://':
            cap = cv2.VideoCapture(input_stream)
        elif input_stream == 'none':
            cap = cv2.VideoCapture(0)
        else:
            cap = cv2.VideoCapture(input_stream)
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            print(fps)
        self.factory = SensorFactory()
        self.factory.init(cap, resolution=GstServer._resolution(cap), fps=fps)
        self.factory.set_shared(True)
        self.set_address(host)
        self.set_service(port)
        self.get_mount_points().add_factory("/%s" % uri, self.factory)
        self.attach(None)

def main(input = 0, host = '0.0.0.0', port = '8554', uri = ""):
    GObject.threads_init()
    Gst.init(None)
    server = GstServer()
    server.start(input, host, port, uri)
    loop = GObject.MainLoop()
    loop.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Gstreamer RTSP server")
    parser.add_argument("input", type=str, default='0')
    parser.add_argument("host", type=str, default='0.0.0.0')
    parser.add_argument("port", type=str, default='8554')
    parser.add_argument("uri", type=str, default='test')
    args = parser.parse_args()

    main(args.input, args.host, args.port, args.uri)

