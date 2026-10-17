import json, sys, os, subprocess, hashlib, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_demo as md
from kokoro_onnx import Kokoro
SP = os.path.dirname(os.path.abspath(__file__)); M = SP + '/tts_models/'
spec = json.load(open(sys.argv[2])); out = sys.argv[1]
voice = spec.get('voice', 'am_michael'); speed = spec.get('speed', 0.95); pace = spec.get('pace', 1.0); gap = spec.get('gap', 1.0)
k = Kokoro(M + 'kokoro-quantized.onnx', M + 'voices.npz'); os.makedirs(SP + '/tts_cache', exist_ok=True)
clips = []
for sc in spec['scenes']:
    h = hashlib.md5((voice + str(speed) + sc['say']).encode()).hexdigest()[:12]; f = f'{SP}/tts_cache/{h}.wav'
    if not os.path.exists(f):
        a, sr = k.create(sc['say'], voice=voice, speed=speed, lang='en-us'); sf.write(f, a, sr)
    a, sr = sf.read(f, dtype='float32'); clips.append((a, sr))
    base = md.RENDER[sc['type']][1](sc) * pace
    sc['dur'] = round(max(base, len(a) / sr + gap + 0.5), 2)
    print(sc['type'], 'voice', round(len(a) / sr, 1), 'scene', sc['dur'])
md.set_palette(spec.get('palette'))
raw = out.replace('.mp4', '_raw.mp4')
md.render(spec['scenes'], raw, bg_image=spec.get('bg'), bg_dark=spec.get('bg_dark', 0.78), bg_video=spec.get('bg_video'), pace=pace)
sr = clips[0][1]; total = sum(sc['dur'] for sc in spec['scenes']); track = np.zeros(int((total + 1) * sr), dtype=np.float32); t0 = 0.0
for sc, (a, _) in zip(spec['scenes'], clips):
    i = int((t0 + 0.5) * sr); track[i:i + len(a)] += a; t0 += sc['dur']
peak = np.abs(track).max(); track = track / peak * 0.89
sf.write(out.replace('.mp4', '_voice.wav'), track, sr)
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-i', out.replace('.mp4', '_voice.wav'), '-vf', 'hqdn3d=1.5:1.5:6:6', '-c:v', 'libx264', '-preset', 'slow', '-crf', '25', '-pix_fmt', 'yuv420p', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', out], check=True)
json.dump(spec, open(sys.argv[2].replace('.json', '_timed.json'), 'w'), indent=1); print('done', out, round(total, 1), 's')
