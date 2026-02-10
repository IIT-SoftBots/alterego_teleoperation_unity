# ZED Streaming & Rectification

This workspace provides two scripts:
- **ZED SDK dual UDP streamer**: `zed_sdk_streamer.py`
- **OpenCV rectification + quality check**: `opencv_streamer.py`

## Scripts

### 1) ZED SDK UDP streamer
Streams ZED side-by-side frames and splits them into left/right H.264 UDP streams using FFmpeg.

**Behavior**
- Opens ZED at 2K/15 FPS
- Grabs `SIDE_BY_SIDE` frames
- Splits and streams left/right to UDP ports **5000** and **5001**

**Run**
```sh
python3 zed_sdk_streamer.py
```

### 2) OpenCV rectification + alignment check
Loads ZED calibration, rectifies left/right views, and estimates vertical alignment error.

**Behavior**
- Reads calibration from `calibrations/*.conf`
- Rectifies frames and draws alignment lines
- Computes mean vertical error before/after rectification

**Run**
```sh
python3 opencv_streamer.py
```

## Calibration files
Camera calibration configs live in `calibrations/`.

## Docker (optional)
A simple container setup exists in `compose.yaml` to run the ZED streamer.

**Run**
```sh
docker compose up
```