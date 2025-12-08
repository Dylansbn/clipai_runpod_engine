from handler import handler

event = {
    "input": {
        "task": "process",
        "video_url": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4",
        "num_clips": 1
    }
}

resp = handler(event)
print("Réponse handler :", resp)
