#Application to read the thermal camera data and display it on the screen
#Read the data from serial port
#Data format is csv 
#768 pixels in 32x24 format
#Each pixel is corrected temperature in DegC
#Arrange the pixels in a 2x2 array to be displayed as colour according to temperature

#User interface has option for serial port selection
#Option to select the display mode
#Option to select the colour map


from serial.tools.list_ports import comports
import time
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import numpy as np
import cv2 as cv
import configparser
import os
import logging

from ir_serial_reader import IRSerialReader

from constants import *

#config logging to terminal
logging.basicConfig(level=logging.INFO)

#class to do per pixel adaptive filtering
class TemperatureFilter():
    def __init__(self, shape, noise_threshold=1.5):
        self.filtered = np.zeros(shape, dtype=np.float32)
        self.noise_threshold = noise_threshold
        
    def filter(self, data):
        deltas = data - self.filtered
        deltas2 = np.square(deltas)
        gains = deltas2 / (deltas2 + self.noise_threshold**2)
        self.filtered = self.filtered + (gains * deltas)
        return self.filtered
        
        

class IRCamApp(tk.Tk):
    def __init__(self, port="", color_map="jet", *args, **kwargs):
        tk.Tk.__init__(self, *args, **kwargs)
        self.request_disconnect = False
        self.title("IR Camera")
        self.geometry()
        self.port = port
        self.color_map_default = color_map
        self.display_resolution = display_resolutions["640x480"]
        self.unpacker = None
        self.ir_serial_reader = None
        self.baudrate = 460800
        self.frame_counter = 0
        self.line_counter = -1
        self.show_help = False
        self.debug = False
        self.loaded_data = None
        self.paused = False
        self.last_data = None

        self.frame = np.zeros((24, 32), dtype=np.float32)
        self.filter = TemperatureFilter((24, 32))

        #connect destroy event to stop the serial reader
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        #create the widgets
        self.create_widgets()
        
        
    #on delete window event handler to stop servies
    def on_closing(self):
        self.request_disconnect = True
        if self.ir_serial_reader is not None:
            if self.ir_serial_reader.is_alive():
                self.ir_serial_reader.stop()
        self.destroy()
        
    #validation function for value entry widgets  
    def validate(self, action, index, value_if_allowed,
                        prior_value, text, validation_type, trigger_type, widget_name):
            if value_if_allowed:
                try:
                    float(value_if_allowed)
                    return True
                except ValueError:
                    return False
            else:
                return False
        
        
    def create_widgets(self):
        
        padx = 12
        pady = 6
        
        #validation command for value entry widgets
        vcmd = (self.register(self.validate),
                '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')
        
        row = 0
        
        #Load saved capture button
        self.load_capture_button = tk.Button(self, text="Load Capture", command=self.load_capture_data)
        self.load_capture_button.grid(row=row, column=0, columnspan=2, sticky="ew", padx=padx, pady=pady)
                        
        row += 1

        self.port_button = tk.Button(self, text="Connect", command=self.connect)
        self.port_button.grid(row=row, column=0, columnspan=2, sticky="ew", padx=padx, pady=pady*2)
        
        row += 1
        
        self.port_label = tk.Label(self, text="Serial Port")
        self.port_label.grid(row=row, column=0, padx=padx, pady=pady)
        
        #dropdown to select the serial port
        self.port_var = tk.StringVar()
        self.port_var.set(self.port)
        self.port_dropdown = ttk.Combobox(self, textvariable=self.port_var)
        self.port_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #baudrate chooser
        self.baudrate_label = tk.Label(self, text="Baudrate")
        self.baudrate_label.grid(row=row, column=0, padx=padx, pady=pady)
        
        self.baudrate_var = tk.IntVar()
        self.baudrate_var.set(self.baudrate)
        self.baudrate_dropdown = ttk.Combobox(self, textvariable=self.baudrate_var, state="readonly")
        self.baudrate_dropdown["values"] = baudrates
        self.baudrate_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #Pause button
        self.paused_var = tk.BooleanVar()
        self.pause_button = tk.Button(self, text="Pause", command=lambda: self.paused_var.set(not self.paused_var.get()))
        self.pause_button.grid(row=row, column=0, columnspan=2, sticky="ew", padx=padx, pady=pady)
        self.paused_var.set(False)
        
        row += 1
        
        #color maps chooser
        self.color_map_label = tk.Label(self, text="Color Map")
        self.color_map_label.grid(row=row, column=0, padx=padx, pady=pady)
        
        self.color_map_var = tk.StringVar()
        self.color_map_var.set(self.color_map_default)
        self.color_map_dropdown = ttk.Combobox(self, textvariable=self.color_map_var, state="readonly")
        self.color_map_dropdown["values"] = list(color_maps.keys())
        self.color_map_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
                
        #display resolution chooser
        self.display_resolution_label = tk.Label(self, text="Display Resolution")
        self.display_resolution_label.grid(row=row, column=0)
        self.display_resolution_var = tk.StringVar()
        self.display_resolution_var.set(DISPLAY_RESOLUTION_DEFAULT)
        self.display_resolution_dropdown = ttk.Combobox(self, textvariable=self.display_resolution_var, state="readonly")
        self.display_resolution_dropdown["values"] = list(display_resolutions.keys())
        self.display_resolution_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #display interpolation chooser
        self.display_interpolation_label = tk.Label(self, text="Display Interpolation")
        self.display_interpolation_label.grid(row=row, column=0)
        self.display_interpolation_var = tk.StringVar()
        self.display_interpolation_var.set("Cubic")
        self.display_interpolation_dropdown = ttk.Combobox(self, textvariable=self.display_interpolation_var)
        self.display_interpolation_dropdown["values"] = list(display_interpolations.keys())
        self.display_interpolation_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #display autorange checkboxes for min and max
        self.display_min_temp_autorange_var = tk.BooleanVar()
        self.display_min_temp_autorange_checkbox = tk.Checkbutton(self, text="Min Temp Auto", variable=self.display_min_temp_autorange_var)
        self.display_min_temp_autorange_checkbox.grid(row=row, column=0, padx=padx, pady=pady)
        self.display_min_temp_autorange_var.set(MIN_TEMP_AUTORANGE_DEFAULT)
        
        self.display_min_temp_manual_var = tk.DoubleVar()
        self.display_min_temp_manual_var.set(MIN_TEMP_MANUAL_DEFAULT)
        self.display_min_temp_manual_entry = tk.Entry(self, textvariable=self.display_min_temp_manual_var, validate = 'key', validatecommand = vcmd)
        self.display_min_temp_manual_entry.grid(row=row, column=1, padx=padx, pady=pady)
                
        row += 1
        
        self.display_max_temp_autorange_var = tk.BooleanVar()
        self.display_max_temp_autorange_checkbox = tk.Checkbutton(self, text="Max Temp Auto", variable=self.display_max_temp_autorange_var)
        self.display_max_temp_autorange_checkbox.grid(row=row, column=0, padx=padx, pady=pady)
        self.display_max_temp_autorange_var.set(MAX_TEMP_AUTORANGE_DEFAULT)
                
        self.display_max_temp_manual_var = tk.DoubleVar()
        self.display_max_temp_manual_var.set(MAX_TEMP_MANUAL_DEFAULT)
        self.display_max_temp_manual_entry = tk.Entry(self, textvariable=self.display_max_temp_manual_var, validate = 'key', validatecommand = vcmd)
        self.display_max_temp_manual_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #display range headroom
        self.display_range_headroom_label = tk.Label(self, text="Display Range Headroom")
        self.display_range_headroom_label.grid(row=row, column=0, padx=padx, pady=pady)
        self.display_range_headroom_var = tk.DoubleVar()
        self.display_range_headroom_var.set(DISPLAY_RANGE_HEADROOM_DEFAULT)
        
        self.display_range_headroom_entry = tk.Entry(self, textvariable=self.display_range_headroom_var, validate = 'key', validatecommand = vcmd)
        self.display_range_headroom_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #Temperature filter noise threshold
        self.filter_noise_threshold_label = tk.Label(self, text="Filter Noise Threshold")
        self.filter_noise_threshold_label.grid(row=row, column=0, padx=padx, pady=pady)
        self.filter_noise_threshold_var = tk.DoubleVar()
        self.filter_noise_threshold_var.set(FILTER_NOISE_DEFAULT)
        self.filter_noise_threshold_entry = tk.Entry(self, textvariable=self.filter_noise_threshold_var, validate = 'key', validatecommand = vcmd)
        self.filter_noise_threshold_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #Temperature contour tolerance
        self.contour_tolerance_label = tk.Label(self, text="Contour Tolerance %")
        self.contour_tolerance_label.grid(row=row, column=0, padx=padx, pady=pady)
        self.contour_tolerance_var = tk.DoubleVar()
        self.contour_tolerance_var.set(CONTOUR_TOLERANCE_DEFAULT)
        self.contour_tolerance_entry = tk.Entry(self, textvariable=self.contour_tolerance_var, validate = 'key', validatecommand = vcmd)
        self.contour_tolerance_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        #show ticks on the temperature scale
        self.show_scale_ticks_var = tk.BooleanVar()
        self.show_scale_ticks_checkbox = tk.Checkbutton(self, text="Show Scale Ticks", variable=self.show_scale_ticks_var)
        self.show_scale_ticks_checkbox.grid(row=row, column=0, padx=padx, pady=pady)
        self.show_scale_ticks_var.set(SHOW_SCALE_TICKS_DEFAULT)
                
        #show contours checkbox
        self.show_contours_var = tk.BooleanVar()
        self.show_contours_checkbox = tk.Checkbutton(self, text="Show Contours", variable=self.show_contours_var)
        self.show_contours_checkbox.grid(row=row, column=1, padx=padx, pady=pady)
        self.show_contours_var.set(SHOW_CONTOURS_DEFAULT)
                
        self.update_serial_ports()
        
    def load_capture_data(self):
        folderpath = os.path.join(os.getcwd(), "capture")
        filepath = filedialog.askopenfilename(initialdir=folderpath, title="Select file", filetypes=(("CSV data files", "*.csv"), ("all files", "*.*")))
        if not filepath:
            return
        #load csv data
        self.loaded_data = np.loadtxt(filepath, delimiter=",")
        self.refresh_loaded_data()
        
    def refresh_loaded_data(self):
        if self.loaded_data is None:
            return
        self._display_data(self.loaded_data)
        self.after(100, self.refresh_loaded_data)                
        
    def update_serial_ports(self):
        self.port_dropdown["values"] = []
        ports = comports()
        for port, desc, hwid in sorted(ports):
            print("{}: {} [{}]".format(port, desc, hwid))
            self.port_dropdown["values"] = [port for port, desc, hwid in ports]
    
    def connect(self):
        self.request_disconnect = False
        port = self.port_var.get()       
        self.ir_serial_reader = IRSerialReader(port, self.baudrate)
        self.port_button.config(text="Disconnect", command=self.disconnect)
        self.baudrate_dropdown.config(state="disabled")
        self.port_dropdown.config(state="disabled")
        self._read_data()
        
    def disconnect(self):
        self.request_disconnect = True
        
    def _read_data(self):
        if self.request_disconnect:
            self.ir_serial_reader.stop()
            self.ir_serial_reader = None
            cv.destroyAllWindows()
            self.port_button.config(text="Connect", command=self.connect)
            self.baudrate_dropdown.config(state="readonly")
            self.port_dropdown.config(state="readonly")
            return
        
        if not self.ir_serial_reader.is_alive():
            return
        
        data = self.ir_serial_reader.rx_queue.get(10)
        if data is not None:
            self.loaded_data = None
            self._process_data(data)                    

        self.after(10, self._read_data)


    def _process_data(self, data):
        data = np.array(data, dtype=np.float32)
        self._display_data(data)
    
    
    def input_pixel_to_output_pixel(self, x, y):
        #convert input pixel to output pixel
        #input pixel is 32x24
        #output pixel is self.display_resolution
        output_x = int((x+0.5) * self.display_resolution[0] / 32)
        output_y = int((y+0.5) * self.display_resolution[1] / 24)
        return output_x, output_y

    def input_pixels_to_output_pixels(self, temp_pos):
        out_px = (temp_pos + 0.5) * self.display_resolution[1] / 24
        out_px = np.round(out_px).astype(np.int64)
        return out_px
    
    def get_display_range(self, min_temp, max_temp):
        display_min_range = self.display_min_temp_manual_var.get()
        display_max_range = self.display_max_temp_manual_var.get()

        display_range_headroom = self.display_range_headroom_var.get()

        if self.display_min_temp_autorange_var.get():
            display_min_range = min_temp - display_range_headroom

        if self.display_max_temp_autorange_var.get():
            display_max_range = max_temp + display_range_headroom
        
        display_range = display_max_range - display_min_range
        return display_range, display_min_range, display_max_range

    
    def normalize_temperature_data(self, data, min_temp, max_temp):
        normalized = (data - min_temp) / (max_temp - min_temp)
        return normalized
    
    def temperature_to_scale_normalized(self, normalized_temp, display_range, display_max_range):
        normalized_scale = display_range / 23
        display_scale_temp = (display_max_range - normalized_temp) / normalized_scale
        return display_scale_temp
    
    def draw_hotspot(self, position, rgb, fg=(255, 255, 255), bg=(0, 0, 0)):
        xres = rgb.shape[1]
        circle_size = int(xres*0.005) + 4
        cv.circle(rgb, position, circle_size, bg, 4)
        cv.circle(rgb, position, circle_size, fg, 2)
    
    def _display_data(self, data):
        try:
            data = data.reshape(24, 32)            
        except Exception as e:
            logging.warning("Error reshaping data: %s" % e)
            return

        try:
            noise_threshold = self.filter_noise_threshold_var.get()
            if noise_threshold > 0 and noise_threshold < 1000:
                self.filter.noise_threshold = noise_threshold
        except:
            pass
        
        #filter new data for every frame, even when paused
        data = self.filter.filter(data)
        
        #update display resolution
        display_resolution_var = self.display_resolution_var.get()
        self.display_resolution = display_resolutions[display_resolution_var]
                
        #reverse the x axis
        data = np.fliplr(data)
        
        if self.paused_var.get():
            data = self.last_data
        
        self.last_data = data
        
        min_temp = np.min(data)
        max_temp = np.max(data)
        
        display_range, display_min_range, display_max_range = self.get_display_range(min_temp, max_temp)
        
        normalized = self.normalize_temperature_data(data, display_min_range, display_max_range)

        #limit the range to 0-1
        normalized = np.clip(normalized, 0, 1)        
        
        #convert array to CV_8UC1
        cv_normalized = np.array(normalized * 255, dtype=np.uint8)
        
        color_map_str = self.color_map_var.get()
        color_map = color_maps[color_map_str]
        rgb = cv.applyColorMap(cv_normalized, color_map)
        
        #rescale the image to self.display_resolution_var
        display_interpolation = display_interpolations[self.display_interpolation_var.get()]
        rgb = cv.resize(rgb, self.display_resolution, interpolation=display_interpolation)

        #find index of min and max temp
        min_index = np.unravel_index(np.argmin(data), data.shape)
        max_index = np.unravel_index(np.argmax(data), data.shape)

        #swapaxis on the index
        min_index = min_index[::-1]
        max_index = max_index[::-1]
        
        min_pixel_position = self.input_pixel_to_output_pixel(*min_index)
        max_pixel_position = self.input_pixel_to_output_pixel(*max_index)

        #Make temperature scale
        temp_scale_width_px = int(20 * self.display_resolution[0] / 640)
        temp_scale_size = (temp_scale_width_px, self.display_resolution[1])
        temp_scale = self.make_temp_scale(color_map, display_interpolation, temp_scale_size)
                
        #add the temperature scale to the left side of the image
        rgb[:, :temp_scale_width_px] = temp_scale
        
        min_temp_normalized_pos = self.temperature_to_scale_normalized(min_temp, display_range, display_max_range)
        max_temp_normalized_pos = self.temperature_to_scale_normalized(max_temp, display_range, display_max_range)
        
        min_temp_position = self.input_pixel_to_output_pixel(x=0, y=min_temp_normalized_pos)
        max_temp_position = self.input_pixel_to_output_pixel(x=0, y=max_temp_normalized_pos)
        
        #print min and max temp
        text_size = 0.5
        text_y_offset = 5
        text_xpos = temp_scale_width_px+10
        
        if self.show_scale_ticks_var.get():
            self.draw_ticks(rgb, display_min_range, display_max_range, temp_scale_width_px, text_xpos, text_y_offset, text_size)

        self.draw_hotspot(min_temp_position, rgb, fg=(0, 0, 0), bg=(255, 255, 255))
        self.draw_hotspot(max_temp_position, rgb, fg=(255, 255, 255), bg=(0, 0, 0))

        cv.putText(rgb, "%.1f" % max_temp, (text_xpos, max_temp_position[1]+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (255, 255, 255), 3)
        cv.putText(rgb, "%.1f" % max_temp, (text_xpos, max_temp_position[1]+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (0, 0, 0), 2)

        cv.putText(rgb, "%.1f" % min_temp, (text_xpos, min_temp_position[1]+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (255, 255, 255), 3)
        cv.putText(rgb, "%.1f" % min_temp, (text_xpos, min_temp_position[1]+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (0, 0, 0), 2)

        
        if self.show_help:
            #draw help table on the image
            help_x = 150
            help_y = 20
            help_line_height = 20
            for line in help_table:
                cv.putText(rgb, line[0], (help_x, help_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                cv.putText(rgb, line[1], (help_x + 100, help_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                help_y += help_line_height     
        

        #draw min and max pixel circles on the image
        self.draw_hotspot(min_pixel_position, rgb, fg=(0, 0, 0), bg=(255, 255, 255))
        self.draw_hotspot(max_pixel_position, rgb, fg=(255, 255, 255), bg=(0, 0, 0))

                        
        if self.show_contours_var.get():
            self.draw_contours(data, max_temp, min_temp, max_pixel_position, min_pixel_position, rgb)
        
        if not self.debug:
            try:
                cv.destroyWindow("High Temperatures")
            except:
                pass
            try:
                cv.destroyWindow("Low Temperatures")
            except:
                pass

        #If not in help mode show the help hint at the bottom
        if not self.show_help:
            cv.putText(rgb, "H for help", (self.display_resolution[0]-100, self.display_resolution[1] - 10), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            
        #If debugging then show it at the bottom
        if self.debug:
            cv.putText(rgb, "Debug mode", (self.display_resolution[0]-100, self.display_resolution[1] - 30), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
            
        
        #Use cv to show the image
        cv.imshow("IR Camera", rgb)
        key = cv.waitKey(50)
        
        #capitalize the key
        
        if key == 27 or key == ord("q") or key == ord("Q"):
            cv.destroyAllWindows()
            #close the app
            self.on_closing()
        elif key == ord("c") or key == ord("C"):
            #capture the image to the capture folder with timestamp
            folderpath = os.path.join(os.getcwd(), "capture")
            os.makedirs(folderpath, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = "ir_cam_%s.png" % timestamp
            filepath = os.path.join(folderpath, filename)
            cv.imwrite(filepath, rgb)
            #write the data to a csv file in the same folder
            data_filename = "ir_cam_%s.csv" % timestamp
            data_filepath = os.path.join(folderpath, data_filename)
            np.savetxt(data_filepath, data, delimiter=",", fmt="%.2f")
        elif key == ord("p") or key == ord(" ") or key == ord("P"):
            #pause the display
            self.paused_var.set(not self.paused_var.get())
        elif key == ord("d") or key == ord("D"):
            #cycle through the display sizes/resolutions
            res_keys = list(display_resolutions.keys())
            res_index = res_keys.index("%dx%d" % tuple(self.display_resolution))
            res_index = (res_index + 1) % len(res_keys)
            self.display_resolution_var.set(res_keys[res_index])
        elif key == ord("m") or key == ord("M"):
            #cycle through the color maps
            cmap_keys = list(color_maps.keys())
            cmap_index = cmap_keys.index(self.color_map_var.get())
            cmap_index = (cmap_index + 1) % len(cmap_keys)
            self.color_map_var.set(cmap_keys[cmap_index])
        elif key == ord("t") or key == ord("T"):
            #toggle show temperature contours
            self.show_contours_var.set(not self.show_contours_var.get())
        elif key == ord("h") or key == ord("H"):
            self.show_help = not self.show_help
        elif key == ord("b") or key == ord("B"):
            self.debug = not self.debug
        elif key == ord("k") or key == ord("K"):
            self.show_scale_ticks_var.set(not self.show_scale_ticks_var.get())
        

    def make_temp_scale(self, color_map, display_interpolation, temp_scale_size):
        #make the a color temperature scale from 255 to 0
        temp_scale = np.linspace(start=255, stop=0, num=24).T
        
        #convert the scale to CV_8UC1
        temp_scale = np.array(temp_scale, dtype=np.uint8)
        
        #rescale the temperature scale to the display resolution
        temp_scale = cv.resize(temp_scale, (temp_scale_size[0], temp_scale_size[1]), interpolation=display_interpolation)
        
        #convert the temperature scale to a color map
        temp_scale = cv.applyColorMap(temp_scale, color_map)

        return temp_scale
    
    
    def draw_contours(self, data, max_temp, min_temp, max_pixel_position, min_pixel_position, rgb):
        temp_range = max_temp - min_temp
        
        contour_tolerance = self.contour_tolerance_var.get()
        contour_tolerance = np.clip(contour_tolerance, 0, 100)
        contour_tolerance *= 0.01
        
        #data with temperature above 90% of the range
        high_temperatures = data > (max_temp - contour_tolerance * temp_range)
        
        #data with temperature below 10% of the range
        low_temperatures = data < (min_temp + contour_tolerance * temp_range)
        
        #convert the data to CV_8UC1
        high_temperatures = np.array(high_temperatures * 255, dtype=np.uint8)
        low_temperatures = np.array(low_temperatures * 255, dtype=np.uint8)
        
        #scale the high and low temperature pixels to the display resolution
        display_interpolation = display_interpolations[self.display_interpolation_var.get()]
        high_temperatures = cv.resize(high_temperatures, self.display_resolution, interpolation=display_interpolation)
        low_temperatures = cv.resize(low_temperatures, self.display_resolution, interpolation=display_interpolation)

        blur_size = int(self.display_resolution[0] * 0.02)
        if blur_size % 2 == 0:
            blur_size += 1

        #gaussian blur the high and low temperature pixels
        high_temperatures = cv.GaussianBlur(high_temperatures, (blur_size, blur_size), 0)
        low_temperatures = cv.GaussianBlur(low_temperatures, (blur_size, blur_size), 0)
                                
        #make contours of the high and low temperature pixels
        high_contours, _ = cv.findContours(high_temperatures, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        low_contours, _ = cv.findContours(low_temperatures, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

        #choose contours containing the max and min pixel
        high_contours = [c for c in high_contours if cv.pointPolygonTest(c, max_pixel_position, False) >= 0]
        low_contours = [c for c in low_contours if cv.pointPolygonTest(c, min_pixel_position, False) >= 0]
        
        #draw the contours on the image
        cv.drawContours(rgb, high_contours, -1, (255, 255, 255), 2)
        cv.drawContours(rgb, low_contours, -1, (0, 0, 0), 2)
        
        if self.debug:
            #show the high and low temperature pixels
            cv.imshow("High Temperatures", high_temperatures)
            cv.imshow("Low Temperatures", low_temperatures)

    def draw_ticks(self, rgb, display_min_range, display_max_range, temp_scale_width_px, text_xpos, text_y_offset, text_size):
        display_range = display_max_range - display_min_range
        
        #Find the nearest decade to the temperatue range
        decade = 5 ** int(np.log(display_range)/np.log(5))
        
        #Floor the min display range to the nearest decade
        display_min_tick = np.floor(display_min_range / decade) * decade
        
        #Ceil the max display range to the nearest decade
        display_max_tick = np.ceil(display_max_range / decade) * decade

        #make a range of ticks from min to max with decade spacing
        num_ticks = int((display_max_tick - display_min_tick) / decade)
        tick_temperatures = np.linspace(display_min_tick, display_max_tick, num_ticks+1)
            
        #Find the tick temperature locations normalized to the temperature input scale 0-1
#            tick_temperatures_normalized = self.normalize_temperature_data(tick_temperatures, display_min_range, display_max_range)
                    
        # Convert temperature input scale to display output scale
        tick_scale_positions = self.temperature_to_scale_normalized(tick_temperatures, display_range, display_max_range)

        #Convert the display scale positions to pixel positions
        # tick_scale_positions = [self.input_pixel_to_output_pixel(x=0, y=pos) for pos in tick_scale_positions]
        tick_positions_px = self.input_pixels_to_output_pixels(tick_scale_positions)
        
        if decade < 1:
            format = "%.1f"
        else:
            format = "%.0f"
        
        #Draw the ticks on the image
        for tick_position, tick_temperature in zip(tick_positions_px, tick_temperatures):
            cv.line(rgb, (0, tick_position), (temp_scale_width_px, tick_position), (255, 255, 255), 3)
            cv.putText(rgb, format % tick_temperature, (text_xpos+10, tick_position+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (255, 255, 255), 3)
            cv.putText(rgb, format % tick_temperature, (text_xpos+10, tick_position+text_y_offset), cv.FONT_HERSHEY_SIMPLEX, text_size, (0, 0, 0), 2)            
            
def main():
    config = configparser.ConfigParser()
    #add config for last used port
    config.add_section("Serial")
    config.set("Serial", "port", "")
    config.add_section("Display")
    config.set("Display", "color_map", "Jet")
    
    config.read("ir_cam.ini")
    port = config.get("Serial", "port")
    color_map = config.get("Display", "color_map")
    
    app = IRCamApp(port=port, color_map=color_map)    
    app.mainloop()
    
    config.set("Serial", "port", app.port_var.get())
    config.set("Display", "color_map", app.color_map_var.get())
    
    with open("ir_cam.ini", "w") as f:
        config.write(f)
    
if __name__ == "__main__":
    main()   
