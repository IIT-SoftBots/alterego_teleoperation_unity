import pyzed.sl as sl
import cv2
import subprocess

# Create a ZED camera object
zed = sl.Camera()

# Set configuration parameters
init_params = sl.InitParameters()
init_params.camera_resolution = sl.RESOLUTION.HD2K # Use 2K HD resolution
init_params.camera_fps = 15

# Open the camera
err = zed.open(init_params)
if err != sl.ERROR_CODE.SUCCESS:
    exit(-1)

# Get resolution and setup UDP streamer (H264 over FFmpeg)
camera_info = zed.get_camera_information()
res = camera_info.camera_configuration.resolution
stream_w, stream_h = res.width * 2, res.height  # SIDE_BY_SIDE is double width
fps = int(init_params.camera_fps)

# Configuration for double stream (Left and Right split)
ip_pilot = "127.0.0.1"      # Indirizzo IP di destinazione
port_l = 5000               # Porta per stream Sinistro
port_r = 5001               # Porta per stream Destro
v_bitrate = "4M"            # Bitrate video
gop_size = fps              # Intervallo I-frame (1 keyframe al secondo)
w, h = res.width, res.height

# FFmpeg command optimized for low-delay dual-stream
ffmpeg_cmd = [
    'ffmpeg',
    '-y',
    '-f', 'rawvideo',
    '-vcodec', 'rawvideo',
    '-pix_fmt', 'bgr24',
    '-s', f"{stream_w}x{stream_h}",
    '-r', str(fps),
    '-i', '-',
    '-filter_complex', f"[0:v]crop={w}:{h}:0:0[out1]; [0:v]crop={w}:{h}:{w}:0[out2]",
    
    # Left Stream output
    '-map', '[out1]',
    '-fflags', 'nobuffer', '-flags', 'low_delay',
    '-mpegts_flags', 'resend_headers',
    '-muxdelay', '0', '-muxpreload', '0', '-max_delay', '0',
    '-g', str(gop_size), 
    '-c:v', 'libx264', 
    '-preset', 'ultrafast', 
    '-tune', 'zerolatency',
    '-x264-params', f"repeat-headers=1:keyint={gop_size}:min-keyint={gop_size}:scenecut=0",
    '-refs', '1', '-bf', '0', '-b:v', v_bitrate,
    '-bsf:v', 'dump_extra',
    '-f', 'mpegts', f'udp://{ip_pilot}:{port_l}?pkt_size=1316&fifo_size=5000000&overrun_nonfatal=1',
    
    # Right Stream output
    '-map', '[out2]',
    '-fflags', 'nobuffer', '-flags', 'low_delay',
    '-mpegts_flags', 'resend_headers',
    '-muxdelay', '0', '-muxpreload', '0', '-max_delay', '0',
    '-g', str(gop_size), 
    '-c:v', 'libx264', 
    '-preset', 'ultrafast', 
    '-tune', 'zerolatency',
    '-x264-params', f"repeat-headers=1:keyint={gop_size}:min-keyint={gop_size}:scenecut=0",
    '-refs', '1', '-bf', '0', '-b:v', v_bitrate,
    '-bsf:v', 'dump_extra',
    '-f', 'mpegts', f'udp://{ip_pilot}:{port_r}?pkt_size=1316&fifo_size=5000000&overrun_nonfatal=1'
]

# Avvio del processo FFmpeg
proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

image = sl.Mat()
runtime_parameters = sl.RuntimeParameters()

try:
    while True:
        if zed.grab(runtime_parameters) == sl.ERROR_CODE.SUCCESS:
            # Recupera l'immagine SIDE_BY_SIDE dalla ZED
            zed.retrieve_image(image, sl.VIEW.SIDE_BY_SIDE)

            # Converti da BGRA (ZED) a BGR (FFmpeg) e invia alla pipe
            frame_bgr = cv2.cvtColor(image.get_data(), cv2.COLOR_BGRA2BGR)
            proc.stdin.write(frame_bgr.tobytes())

except KeyboardInterrupt:
    print("\nInterruzione richiesta dall'utente...")
finally:
    # Pulizia
    if proc:
        proc.stdin.close()
        proc.wait()
    zed.close()