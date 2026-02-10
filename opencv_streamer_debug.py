import cv2
import numpy as np
import configparser
import os
import sys

##########################################################################################################
# Settings - Update these paths and resolution as needed for your specific ZED camera and calibration file.
CALIBRATION_PATH = 'calibrations/SN12934538.conf' #SN17596512.conf'
RESOLUTION = 'HD' # Change to '2K', 'FHD', 'HD', or 'VGA'
##########################################################################################################


def get_zed_params(config_file, resolution='HD'):
    """
    Parses the ZED .conf file and returns OpenCV-compatible camera parameters.
    """
    if not os.path.exists(config_file):
        print(f"Error: Config file {config_file} not found.")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_file)
    
    res = resolution.upper()
    left_cam = f'LEFT_CAM_{res}'
    right_cam = f'RIGHT_CAM_{res}'
    
    if left_cam not in config:
        print(f"Error: Resolution {res} not found in config.")
        sys.exit(1)

    # Intrinsic matrices
    K_l = np.array([
        [float(config[left_cam]['fx']), 0, float(config[left_cam]['cx'])],
        [0, float(config[left_cam]['fy']), float(config[left_cam]['cy'])],
        [0, 0, 1]
    ], dtype=np.float64)
    
    K_r = np.array([
        [float(config[right_cam]['fx']), 0, float(config[right_cam]['cx'])],
        [0, float(config[right_cam]['fy']), float(config[right_cam]['cy'])],
        [0, 0, 1]
    ], dtype=np.float64)
    
    # Distortion coefficients (k1, k2, p1, p2, k3)
    # In ZED files, k1, k2 are radial; k3, k4 are tangential (p1, p2).
    D_l = np.array([
        float(config[left_cam]['k1']),
        float(config[left_cam]['k2']),
        float(config[left_cam]['k3']), # p1
        float(config[left_cam]['k4']), # p2
        0.0 # k3 radial
    ], dtype=np.float64)
    
    D_r = np.array([
        float(config[right_cam]['k1']),
        float(config[right_cam]['k2']),
        float(config[right_cam]['k3']), # p1
        float(config[right_cam]['k4']), # p2
        0.0 # k3 radial
    ], dtype=np.float64)
    
    # Stereo parameters
    stereo = config['STEREO']
    baseline = float(stereo['Baseline'])
    ty = float(stereo['TY'])
    tz = float(stereo['TZ'])
    
    # ZED .conf files often have resolution-specific stereo parameters
    rx = float(stereo.get(f'RX_{res}', stereo.get('RX', 0)))
    cv = float(stereo.get(f'CV_{res}', stereo.get('CV', 0))) # Convergence (Yaw)
    rz = float(stereo.get(f'RZ_{res}', stereo.get('RZ', 0))) # Roll
    
    # Rotation matrix (Euler angles: Z-Y-X order)
    R_x = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)]
    ])
    R_y = np.array([
        [np.cos(cv), 0, np.sin(cv)],
        [0, 1, 0],
        [-np.sin(cv), 0, np.cos(cv)]
    ])
    R_z = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1]
    ])
    
    # R is the rotation of the right camera relative to the left
    R = R_z @ R_y @ R_x
    # T is the translation of the right camera relative to the left
    T = np.array([-baseline, ty, tz])
    
    return K_l, D_l, K_r, D_r, R, T

def check_calibration_quality(rect_l, rect_r):
    # Convert to grayscale
    gray_l = cv2.cvtColor(rect_l, cv2.COLOR_BGR2GRAY)
    gray_r = cv2.cvtColor(rect_r, cv2.COLOR_BGR2GRAY)
    
    # Detect features
    orb = cv2.ORB_create()
    kp1, des1 = orb.detectAndCompute(gray_l, None)
    kp2, des2 = orb.detectAndCompute(gray_r, None)
    
    if des1 is None or des2 is None:
        return None

    # Match features
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    
    # Sort by distance
    matches = sorted(matches, key = lambda x:x.distance)
    
    # Keep top matches
    good_matches = matches[:50]
    
    if not good_matches:
        return None
        
    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])
    
    # Calculate vertical geometric difference (should be 0 for perfect rectification)
    vertical_diffs = np.abs(pts1[:, 1] - pts2[:, 1])
    
    mean_error = np.mean(vertical_diffs)
    
    return mean_error, len(good_matches)

def main():
    # Use the SN file provided in the workspace
    config_path = CALIBRATION_PATH 
    resolution = RESOLUTION
    
    # Image size for HD (1280x720)
    res_w, res_h = 1280, 720
    if resolution == '2K': res_w, res_h = 2208, 1242
    elif resolution == 'FHD': res_w, res_h = 1920, 1080
    elif resolution == 'VGA': res_w, res_h = 672, 376

    print(f"Loading calibration for {resolution} from {config_path}...")
    K_l, D_l, K_r, D_r, R, T = get_zed_params(config_path, resolution)
    
    # Stereo Rectification
    # This computes the rotation matrices for rectification (R1, R2) 
    # and new projection matrices (P1, P2).
    R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
        K_l, D_l, K_r, D_r, (res_w, res_h), R, T, alpha=0
    )
    
    # Generate mapping for remap()
    map_l1, map_l2 = cv2.initUndistortRectifyMap(K_l, D_l, R1, P1, (res_w, res_h), cv2.CV_32FC1)
    map_r1, map_r2 = cv2.initUndistortRectifyMap(K_r, D_r, R2, P2, (res_w, res_h), cv2.CV_32FC1)
    
    # Open Video Source (Default to ZED camera on ID 4)
    # Note: ZED provides images in Side-By-Side (SBS) format.
    device_id = 4
    cap = cv2.VideoCapture(device_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, res_w * 2)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res_h)
    
    if not cap.isOpened():
        print(f"Warning: Could not open camera on ID {device_id}. Trying ID 0...")
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, res_w * 2)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res_h)

    if not cap.isOpened():
        print("Error: Could not open ZED camera. Please check connection or ID.")
        return

    print("Press 'q' to exit. Green lines help check horizontal alignment.")
    
    is_headless = 'DISPLAY' not in os.environ
    if is_headless:
        print("Headless mode detected. Saving the first processed frame to 'result_rectified.jpg' and exiting.")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
            
        # Split Side-By-Side frame into Left and Right
        h_orig, w_orig, _ = frame.shape
        img_l = frame[:, :w_orig//2]
        img_r = frame[:, w_orig//2:]
        
        # Resize to calibration resolution if necessary
        if (w_orig//2 != res_w) or (h_orig != res_h):
            img_l = cv2.resize(img_l, (res_w, res_h))
            img_r = cv2.resize(img_r, (res_w, res_h))
        
        # Apply rectification (calibration)
        rect_l = cv2.remap(img_l, map_l1, map_l2, cv2.INTER_LINEAR)
        rect_r = cv2.remap(img_r, map_r1, map_r2, cv2.INTER_LINEAR)
        
        # Prepare visualization
        before = np.hstack((img_l, img_r))
        after = np.hstack((rect_l, rect_r))
        
        # Check calibration quality (Before)
        quality_before = check_calibration_quality(img_l, img_r)
        if quality_before:
            mean_err_b, num_matches_b = quality_before
            text_b = f"Mean Vertical Error: {mean_err_b:.2f} px ({num_matches_b} matches)"
            cv2.putText(before, text_b, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # Check calibration quality (After)
        quality_after = check_calibration_quality(rect_l, rect_r)
        if quality_after:
            mean_err_a, num_matches_a = quality_after
            text_a = f"Mean Vertical Error: {mean_err_a:.2f} px ({num_matches_a} matches)"
            cv2.putText(after, text_a, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Print comparison if both available
            if quality_before:
                print(f"Vertical Error - Before: {mean_err_b:.2f} px | After: {mean_err_a:.2f} px")
            else:
                print(text_a)

        # Resize for display 
        display_scale = 0.5
        before_disp = cv2.resize(before, (0, 0), fx=display_scale, fy=display_scale)
        after_disp = cv2.resize(after, (0, 0), fx=display_scale, fy=display_scale)
        
        # Draw horizontal lines for alignment check on 'after'
        for i in range(0, after_disp.shape[0], 20):
            cv2.line(after_disp, (0, i), (after_disp.shape[1], i), (0, 255, 0), 1)
            
        if is_headless:
            # Combine before and after vertically for the saved image
            combined = np.vstack((before_disp, after_disp))
            cv2.imwrite('result_rectified.jpg', combined)
            print("Successfully saved result_rectified.jpg")
            break

        cv2.imshow("Before (Raw SBS)", before_disp)
        cv2.imshow("After (Rectified SBS)", after_disp)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
