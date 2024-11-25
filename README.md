Takes temperature data from a 32x24 pixel MLX90640 infra-red camera sensor and visualizes it.

Data is delivered from the sensor through serial port in msgpack packets for bandwidth efficieny.

https://msgpack.org/index.html

Each line of pixels is in array format with int16 type:

[frame count, line count, x0 , x1, x2, ...., x31]
