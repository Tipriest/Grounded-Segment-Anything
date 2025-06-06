import os
import sys

sys.path.append(os.path.join(os.getcwd(), "GroundingDINO"))
# If you have multiple GPUs, you can set the GPU to use here.
# The default is to use the first GPU, which is usually GPU 0.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import numpy as np
import torch
from PIL import Image
from huggingface_hub import hf_hub_download

# Grounding DINO
from GroundingDINO.groundingdino.models import build_model
from GroundingDINO.groundingdino.util import box_ops
from GroundingDINO.groundingdino.util.slconfig import SLConfig
from GroundingDINO.groundingdino.util.utils import (
    clean_state_dict,
)
from GroundingDINO.groundingdino.util.inference import (
    annotate,
    load_image,
    predict,
)

# segment anything
from segment_anything import build_sam, SamPredictor


def load_model_hf(repo_id, filename, _ckpt_config_filename, device="cpu"):
    cache_config_file = hf_hub_download(
        repo_id=repo_id, filename=_ckpt_config_filename
    )

    args = SLConfig.fromfile(cache_config_file)
    model = build_model(args)
    args.device = device

    cache_file = hf_hub_download(repo_id=repo_id, filename=filename)
    checkpoint = torch.load(cache_file, map_location="cpu")
    log = model.load_state_dict(
        clean_state_dict(checkpoint["model"]), strict=False
    )
    print(f"Model loaded from {cache_file} \n => {log}")
    _ = model.eval()
    return model


def show_mask(mask, _image, random_color=True):
    if random_color:
        color = np.concatenate([np.random.random(3), np.array([0.8])], axis=0)
    else:
        color = np.array([30 / 255, 144 / 255, 255 / 255, 0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)

    annotated_frame_pil = Image.fromarray(_image).convert("RGBA")
    mask_image_pil = Image.fromarray(
        (mask_image.cpu().numpy() * 255).astype(np.uint8)
    ).convert("RGBA")

    return np.array(Image.alpha_composite(annotated_frame_pil, mask_image_pil))


ckpt_repo_id = "ShilongLiu/GroundingDINO"
ckpt_filenmae = "groundingdino_swinb_cogcoor.pth"
ckpt_config_filename = "GroundingDINO_SwinB.cfg.py"
sam_checkpoint = "sam_vit_h_4b8939.pth"
if __name__ == "__main__":
    groundingdino_model = load_model_hf(
        ckpt_repo_id, ckpt_filenmae, ckpt_config_filename
    )
    DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    sam = build_sam(checkpoint=sam_checkpoint)
    sam.to(device=DEVICE)
    sam_predictor = SamPredictor(sam)
    local_image_path = "/home/tipriest/Documents/\
30Days-for-segmentation/steps/1_preprocess/key_frames/000286.jpg"

    TEXT_PROMPT = "curb"
    BOX_TRESHOLD = 0.3
    TEXT_TRESHOLD = 0.25

    image_source, image = load_image(local_image_path)

    boxes, logits, phrases = predict(
        model=groundingdino_model,
        image=image,
        caption=TEXT_PROMPT,
        box_threshold=BOX_TRESHOLD,
        text_threshold=TEXT_TRESHOLD,
        device=DEVICE,
    )

    annotated_frame = annotate(
        image_source=image_source, boxes=boxes, logits=logits, phrases=phrases
    )
    annotated_frame = annotated_frame[..., ::-1]  # BGR to RGB

    # set image
    sam_predictor.set_image(image_source)

    # box: normalized box xywh -> unnormalized xyxy
    H, W, _ = image_source.shape
    boxes_xyxy = box_ops.box_cxcywh_to_xyxy(boxes) * torch.Tensor([W, H, W, H])

    transformed_boxes = sam_predictor.transform.apply_boxes_torch(
        boxes_xyxy, image_source.shape[:2]
    ).to(DEVICE)
    masks, _, _ = sam_predictor.predict_torch(
        point_coords=None,
        point_labels=None,
        boxes=transformed_boxes,
        multimask_output=True,
    )
    for i in range(2):
        for j in range(3):
            
            annotated_frame_with_mask = show_mask(masks[i][j].cpu(), annotated_frame)
            final_image = Image.fromarray(annotated_frame_with_mask)
            final_image.show()
