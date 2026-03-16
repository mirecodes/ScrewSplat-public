# [scripts/make_custom_images.py](file:///mnt/users/hyeslee/codes/baselines/screwsplat/make_custom_images.py) Walkthrough

## Overview
I have successfully implemented [scripts/make_custom_images.py](file:///mnt/users/hyeslee/codes/baselines/screwsplat/make_custom_images.py), which is designed to render an image of a model from a specific joint angle, much like checking URDF joints via `q_values`.

## Changes Made
- Created [scripts/make_custom_images.py](file:///mnt/users/hyeslee/codes/baselines/screwsplat/make_custom_images.py) based around [make_custom_videos.py](file:///mnt/users/hyeslee/codes/baselines/screwsplat/make_custom_videos.py).
- Introduced [ImageConfig](file:///mnt/users/hyeslee/codes/baselines/screwsplat/scripts/make_custom_images.py#18-26) using a `@dataclass`.
- Added command-line arguments: `--model_path` and `--q_values`.
- Replaced the loop over intermediate frames to evaluate a single specific `q_values` setting, which is passed from the argument string.
- The script automatically skips iterating between angles and immediately saves:
  - `geometry_custom.png`
  - `rendered_rgb_custom.png`

## Execution Instructions
You can execute this code by making sure you load the module and specify both the required variables (`model_path` and `q_values`). *Note: Please make sure `nvcc` is exposed properly in your `PATH` by calling `export PATH=/usr/local/cuda/bin:$PATH` before running the script as it heavily relies on GPU rendering via `pycuda`.*

```sh
export PATH=/usr/local/cuda/bin:$PATH
conda activate scrspl310
python scripts/make_custom_images.py \\
    --model_path output/partnet_mobility_blender/bucket/102352/sequential_steps_5_full_48_0.002/06375885-5 \\
    --q_values "1.0"
```

### Result:
- Both `geometry_custom.png` and `rendered_rgb_custom.png` will be generated in your project root where the script was run.
