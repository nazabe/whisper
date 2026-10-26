from fastapi import FastAPI
import os
import json
from faster_whisper import WhisperModel
# from openai import OpenAI  # LLM block is disabled in this legacy script

app = FastAPI()

model_size="small"
device="cpu"
compute_type="int8"

@app.get("/")
def read_root():
    return { "Hello": "World" }

@app.get("/health")
async def read_root():
    return {
        "status": "ok",
        "model": model_size,
        "device": device,
        "compute_type": compute_type,
        "model_loaded": "true"
        }

# TODO: This must receive .mp3 and proccess it.
@app.get("/transcribe")
async def transcribe():

    print('working')
    
    path_input="20261019_fastapi_1.mp3"
    path_output="20261019_fastapi_1.md"

    # small & int8 for CPU
    model = WhisperModel( model_size, device, compute_type) # cpu_threads=8

    segments, info = model.transcribe(path_input, beam_size=5, language="es")

    print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

    with open(path_output, "w", encoding="utf-8") as file:
        
        file.write("# Audio Transcription - %s \n\n" % (path_input))
        file.write("Detected language '%s' with probability %f \n\n" % (info.language, info.language_probability))

        for segment in segments:
            file.write("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))

    # limitations
    # data -> info
    # words, rythm, themes, filler words

    # with open(path_output, "r") as f:
    #     transcription = f.read()

    # TODO: iterate prompt & json format. 

    # with open("prompt.md", "r") as p:
    #     prompt = p.read()

    # client = OpenAI(
    #     api_key=os.environ["DEEPSEEK_API_KEY"],
    #     base_url="https://api.deepseek.com")

    # response = client.chat.completions.create(
    #     model="deepseek-flash",
    #     messages=[
    #         {"role": "system", "content": prompt},
    #         {"role": "user", "content": transcription},
    #     ],
    #     stream=False,
    #     reasoning_effort="high",
    #     extra_body={"thinking": {"type": "enabled"}}
    # )

    # print(response.choices[0].message.content)

    # analisis = json.loads(response.choices[0].message.content)

    # NOTE: JSON for MongoDB 
    # with open("20261005_analisis.json", "w") as f:
    #     json.dump(analisis, f, indent=2, ensure_ascii=False)

    return { "transcribe": "ok" }   
# python --version
# Pyhton 3.12.14

# pip show av
# Name: av
# Version: 19.0.1
# Summary: Pythonic bindings for FFmpeg's libraries.
# Home-page: https://pyav.basswood.io
# Author: 
# Author-email: WyattBlue <wyattblue@auto-editor.com>, Jeremy Lainé <jeremy.laine@m4x.org>
# License-Expression: BSD-3-Clause
# Location: /home/nazareno/Documents/whisper/venv/lib/python3.12/site-packages
# Requires: 
# Required-by: faster-whisper

# pip install "av<14"

# python3 -m venv venv
# source venv/bin/activate