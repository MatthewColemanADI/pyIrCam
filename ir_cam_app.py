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
        gains = deltas2 / (deltas2 + self.noise_threshold)
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
        self.overlay = True
        self.display_resolution = display_resolutions["640x480"]
        self.unpacker = None
        self.ir_serial_reader = None
        self.baudrate = 460800
        self.show_contours = False
        self.frame_counter = 0
        self.line_counter = -1
        self.show_help = False
        self.filter_noise_threshold = 3
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

        self.port_button = tk.Button(self, text="Connect", command=self.connect)
        self.port_button.grid(row=row, column=0, columnspan=2, sticky="ew", padx=padx, pady=pady)
        
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
        
        #color maps chooser
        self.color_map_label = tk.Label(self, text="Color Map")
        self.color_map_label.grid(row=row, column=0, padx=padx, pady=pady)
        
        self.color_map_var = tk.StringVar()
        self.color_map_var.set(self.color_map_default)
        self.color_map_dropdown = ttk.Combobox(self, textvariable=self.color_map_var, state="readonly")
        self.color_map_dropdown["values"] = list(color_maps.keys())
        self.color_map_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        #display resolution chooser
        self.display_resolution_label = tk.Label(self, text="Display Resolution")
        self.display_resolution_label.grid(row=2, column=0)
        self.display_resolution_var = tk.StringVar()
        self.display_resolution_var.set("640x480")
        self.display_resolution_dropdown = ttk.Combobox(self, textvariable=self.display_resolution_var, state="readonly")
        self.display_resolution_dropdown["values"] = list(display_resolutions.keys())
        self.display_resolution_dropdown.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #display interpolation chooser
        self.display_interpolation_label = tk.Label(self, text="Display Interpolation")
        self.display_interpolation_label.grid(row=3, column=0)
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
        self.display_min_temp_autorange_var.set(True)
        
        self.display_min_temp_manual_var = tk.DoubleVar()
        self.display_min_temp_manual_var.set(10)
        self.display_min_temp_manual_entry = tk.Entry(self, textvariable=self.display_min_temp_manual_var, validate = 'key', validatecommand = vcmd)
        self.display_min_temp_manual_entry.grid(row=row, column=1, padx=padx, pady=pady)
                
        row += 1
        
        self.display_max_temp_autorange_var = tk.BooleanVar()
        self.display_max_temp_autorange_checkbox = tk.Checkbutton(self, text="Max Temp Auto", variable=self.display_max_temp_autorange_var)
        self.display_max_temp_autorange_checkbox.grid(row=row, column=0, padx=padx, pady=pady)
        self.display_max_temp_autorange_var.set(True)
                
        self.display_max_temp_manual_var = tk.DoubleVar()
        self.display_max_temp_manual_var.set(40)
        self.display_max_temp_manual_entry = tk.Entry(self, textvariable=self.display_max_temp_manual_var, validate = 'key', validatecommand = vcmd)
        self.display_max_temp_manual_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #display range headroom
        self.display_range_headroom_label = tk.Label(self, text="Display Range Headroom")
        self.display_range_headroom_label.grid(row=row, column=0, padx=padx, pady=pady)
        self.display_range_headroom_var = tk.DoubleVar()
        self.display_range_headroom_var.set(1)
        
        self.display_range_headroom_entry = tk.Entry(self, textvariable=self.display_range_headroom_var, validate = 'key', validatecommand = vcmd)
        self.display_range_headroom_entry.grid(row=row, column=1, padx=padx, pady=pady)
        
        row += 1
        
        #Temperature filter noise threshold
        self.filter_noise_threshold_label = tk.Label(self, text="Filter Noise Threshold")
        self.filter_noise_threshold_label.grid(row=row, column=0, padx=padx, pady=pady)
        self.filter_noise_threshold_var = tk.DoubleVar()
        self.filter_noise_threshold_var.set(self.filter_noise_threshold)
        self.filter_noise_threshold_entry = tk.Entry(self, textvariable=self.filter_noise_threshold_var, validate = 'key', validatecommand = vcmd)
        self.filter_noise_threshold_entry.grid(row=row, column=1, padx=padx, pady=pady)
                
        self.update_serial_ports()
        
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
        self._read_data()
        
    def disconnect(self):
        self.request_disconnect = True
        
    def _read_data(self):
        if self.request_disconnect:
            self.ir_serial_reader.stop()
            self.ir_serial_reader = None
            cv.destroyAllWindows()
            self.port_button.config(text="Connect", command=self.connect)
            return
        
        if not self.ir_serial_reader.is_alive():
            return
        
        data = self.ir_serial_reader.rx_queue.get(10)
        if data is not None:
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
        data = self.filter.filter(data)
        
        #update display resolution
        display_resolution_var = self.display_resolution_var.get()
        self.display_resolution = display_resolutions[display_resolution_var]
                
        #reverse the x axis
        data = np.fliplr(data)
                
        min_temp = np.min(data)
        max_temp = np.max(data)
        
        display_min_range = self.display_min_temp_manual_var.get()
        display_max_range = self.display_max_temp_manual_var.get()

        display_range_headroom = self.display_range_headroom_var.get()

        if self.display_min_temp_autorange_var.get():
            display_min_range = min_temp - display_range_headroom

        if self.display_max_temp_autorange_var.get():
            display_max_range = max_temp + display_range_headroom
        
        range = display_max_range - display_min_range
        normalized = (data - display_min_range) / range
        
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

        #print min and max temp on the image
        cv.putText(rgb, "Min: %.2f" % min_temp, (10, 20), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv.putText(rgb, "Min: %.2f" % min_temp, (10, 20), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        cv.putText(rgb, "Max: %.2f" % max_temp, (10, 40), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv.putText(rgb, "Max: %.2f" % max_temp, (10, 40), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        if self.show_help:
            #draw help table on the image
            help_x = 150
            help_y = 20
            help_line_height = 20
            for line in help_table:
                cv.putText(rgb, line[0], (help_x, help_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                cv.putText(rgb, line[1], (help_x + 100, help_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                help_y += help_line_height        
        
        #add overlay
        if self.overlay:
            
            # #print min and max temp index on the image
            # cv.putText(rgb, "Min idx: %d, %d" % min_index, (10, 60), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            # cv.putText(rgb, "Max idx: %d, %d" % max_index, (10, 80), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
            # #print min and max pixel on the image
            # cv.putText(rgb, "Min px: %d, %d" % min_pixel, (10, 100), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            # cv.putText(rgb, "Max px: %d, %d" % max_pixel, (10, 120), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
            #draw min and max pixel circles on the image
            circle_size = int(self.display_resolution[0]*0.01)
            cv.circle(rgb, min_pixel_position, circle_size, (0, 0, 0), 2)
            cv.circle(rgb, max_pixel_position, circle_size, (255, 255, 255), 2)
            

                        
        if self.show_contours:
            #convert the rgb image to hsv
            hsv = cv.cvtColor(rgb, cv.COLOR_BGR2HSV)
                        
            #get the pixel value of the display for min and max temp
            hsv_max_temp = hsv[max_pixel_position[1], max_pixel_position[0]]
            hsv_min_temp = hsv[min_pixel_position[1], min_pixel_position[0]]
            
            hsv_max_temp_max = hsv_max_temp + [10, 10, 10]
            hsv_max_temp_min = hsv_max_temp - [10, 10, 10]
            hsv_min_temp_max = hsv_min_temp + [10, 10, 10]
            hsv_min_temp_min = hsv_min_temp - [10, 10, 10]
                        
            # #get hue angular distance from hsv to min and max.
            # #wrap around the hue value with maximum 180
            
            #cv mask areas of the image with the min and max pixel values
            mask_max_temp = cv.inRange(hsv, hsv_max_temp_min, hsv_max_temp_max)
            mask_min_temp = cv.inRange(hsv, hsv_min_temp_min, hsv_min_temp_max)
            
            #cv get countours of the masks
            contours_max_temp, _ = cv.findContours(mask_max_temp, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            contours_min_temp, _ = cv.findContours(mask_min_temp, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            
            #choose contours containing the max and min pixel
            contours_max_temp = [c for c in contours_max_temp if cv.pointPolygonTest(c, max_pixel_position, False) >= 0]
            contours_min_temp = [c for c in contours_min_temp if cv.pointPolygonTest(c, min_pixel_position, False) >= 0]
            
            #draw the contours on the image
            cv.drawContours(rgb, contours_max_temp, -1, (255, 255, 255), 2)
            cv.drawContours(rgb, contours_min_temp, -1, (0, 0, 0), 2)
            
            # hue_angulardist_max = hue - hsv_max_temp[0]
            # hue_angulardist_min = np.abs(hsv[:,:,0] - hsv_min_temp[0])
            
            # #find the circular mean of the hue values
            # rect_area_hsv_average[:1] = scitats.circmean(rectangle_sample[:,:,0].flatten(), high=180, low=0)            
            
        #Use cv to show the image
        cv.imshow("IR Camera", rgb)
        key = cv.waitKey(100)
        
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
            cv.waitKey(0)
        elif key == ord("o") or key == ord("O"):
            #enable/disable the information overlay
            self.overlay = not self.overlay
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
            #toggle show contours
            self.show_contours = not self.show_contours
        elif key == ord("h") or key == ord("H"):
            self.show_help = not self.show_help
            
            

        


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
