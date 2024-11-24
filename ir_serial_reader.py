import serial
from threading import Thread, Event
from queue import Queue
import msgpack
import serial
import numpy as np

class IRSerialReader(Thread):
    def __init__(self, port, baudrate):
        Thread.__init__(self)
        self.port = port
        self.baudrate = baudrate
        self.request_disconnect = Event()
        self.unpacker = msgpack.Unpacker()
        self.frame_counter = 0
        self.line_counter = -1
        self.frame = np.zeros((24, 32), dtype=np.float32)
        self.ser = None
        self.data = None
        self.rx_queue = Queue(2)
        
        self.start()
        
    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS)
        except Exception as e:
            logging.error("Error connecting: %s" % e)
            return
        
        self.ser.flushInput()
        
        while not self.request_disconnect.is_set():
            try:
                str_data = self.ser.read(1000)
            except Exception as e:
                logging.error("Error reading data: %s" % e)
                continue

            try:
                self.unpacker.feed(str_data)
            except Exception as e:
                logging.warning("Error feeding data: %s" % e)
                continue

            unpacked = None
            try:
                while(1):
                    unpacked = self.unpacker.unpack()
                    frame_count = unpacked[0]
                    line_count = unpacked[1]
                    temperature_line = np.array(unpacked[2:], dtype=np.float32)
                    temperature_line *= 0.01
                    self.frame[line_count] = temperature_line

                    if line_count != self.line_counter + 1:
                        logging.warning("Missing line: %d of frame %d" % (line_count, self.frame_counter) )

                    self.line_counter = line_count

                    if line_count == 23:
                        self.data = self.frame.flatten()
                        self.frame_counter = frame_count + 1
                        self.line_counter = -1
                        self.rx_queue.put_nowait(self.data)
                        break
                    # elif frame_count != self.frame_counter:
                    #     self.frame_counter = frame_count
                    #     self.line_counter = line_count
                    #     self.data = self.frame.flatten()
                    #     self.rx_queue.put_nowait(self.data)
                    #     break                

                    self.frame_counter = frame_count

            except Exception as e:
                # logging.warning("Error unpacking data: %s" % e)
                pass

        self.ser.close()
        
    def stop(self):
        self.request_disconnect.set()
        self.join()
