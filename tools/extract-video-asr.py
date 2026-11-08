#!/usr/bin/env python3
"""
Agent 0 · 采编 - 视频 ASR 转写工具

通过 yt-dlp 下载视频音频流，用 faster-whisper 进行语音转文字。
适用于页面文本不足、需要视频实际语音内容的场景。

用法：
  python extract-video-asr.py <视频URL> [--model small|medium|large-v3|large-v3-turbo] [--max-duration <分钟>]

依赖：ffmpeg（已安装）+ 本仓库专用虚拟环境 .venv-asr（Python 3.11）
      创建：C:\Users\stars\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv-asr
            .venv-asr\Scripts\python.exe -m pip install faster-whisper yt-dlp
      运行：.venv-asr\Scripts\python.exe tools\extract-video-asr.py <视频URL>

模型：默认 large-v3，加载的是本机离线快照
      E:\data\models\HuggingFace\hub\models--Systran--faster-whisper-large-v3
      （由 resolve_model_dir() 解析成目录路径传给 WhisperModel，不触网、不会 401）
      large-v3-turbo 的上游仓库已私有化，按名字加载会联网并 401，不要当默认值。

输出 JSON 到 stdout：
  {"success": true, "text": "...", "char_count": N, "method": "faster-whisper-<model>", "error": null}
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

# HuggingFace 源配置（优先官方，镜像备用）
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')


def log(msg, file=sys.stderr):
    """日志输出到 stderr，不污染 stdout 的 JSON"""
    print(f'[asr] {msg}', file=file)


def get_video_duration(url):
    """获取视频时长（秒），用于预先判断是否超过限制"""
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--flat-playlist', '-J',
        '--no-playlist',
        '--no-warnings',
        '--quiet',
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if 'entries' in data and data['entries']:
                return data['entries'][0].get('duration', 0)
            return data.get('duration', 0)
    except Exception:
        pass
    return 0


def download_audio(url, output_template, max_duration_min=None):
    """
    用 yt-dlp 下载音频流，返回音频文件路径。
    只下载音频，不下载视频，节省带宽和时间。
    """
    # 先检查时长
    if max_duration_min:
        duration = get_video_duration(url)
        if duration > max_duration_min * 60:
            return None, f'视频时长 {duration//60:.0f} 分钟，超过限制 {max_duration_min} 分钟，跳过 ASR'

    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-f', 'bestaudio/best',          # 只取音频流
        '-x',                             # 提取音频
        '--audio-format', 'wav',          # 转为 WAV
        '--audio-quality', '0',           # 最佳质量
        '--postprocessor-args', 'ffmpeg:-ar 16000 -ac 1 -acodec pcm_s16le',  # 16kHz 单声道
        '-o', output_template,            # 输出路径模板
        '--no-playlist',                  # 不下载播放列表
        '--no-warnings',                  # 减少警告输出
        '--quiet',
        url,
    ]

    log(f'下载音频: {url}')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return None, f'yt-dlp 失败: {result.stderr[:300]}'

        # yt-dlp -o 使用 %(ext)s 模板时，输出路径是 output_template 替换 ext 后的结果
        # 音频提取后扩展名固定为 .wav
        wav_path = output_template.replace('%(ext)s', 'wav')
        if not os.path.exists(wav_path):
            # 查找目录下的 wav 文件
            d = os.path.dirname(output_template)
            if d and os.path.isdir(d):
                wavs = [f for f in os.listdir(d) if f.endswith('.wav')]
                if wavs:
                    wav_path = os.path.join(d, wavs[0])
                else:
                    return None, '音频文件未生成'
            else:
                return None, '音频文件未生成'
        return wav_path, None
    except subprocess.TimeoutExpired:
        return None, '下载超时（>10分钟）'
    except Exception as e:
        return None, f'下载异常: {str(e)}'


def prepare_audio_local(path, tmpdir):
    """
    将本地音视频文件用 ffmpeg 转成 16kHz 单声道 WAV，供 faster-whisper 转写。
    用于 extract-xhs.py 已下载到本地的视频，跳过 yt-dlp 下载。
    """
    wav_path = os.path.join(tmpdir, 'audio.wav')
    log(f'转换本地文件: {path}')
    cmd = [
        'ffmpeg', '-y',
        '-i', path,
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        wav_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return None, f'ffmpeg 转换失败: {result.stderr[:300]}'
        if not os.path.exists(wav_path):
            return None, '音频文件未生成'
        return wav_path, None
    except Exception as e:
        return None, f'本地音频准备失败: {e}'


# 本地模型缓存候选根（按优先级）。HF 仓库名 -> 缓存目录名：把 '/' 换成 '--'
_HF_CACHE_ROOTS = [
    os.environ.get('HF_HOME'),
    r'E:\data\models\HuggingFace',
    os.path.expanduser('~/.cache/huggingface'),
]


def resolve_model_dir(model_name):
    """把模型名解析成已下载的本地快照目录；找不到就原样返回名字（退回联网下载）。

    背景：large-v3-turbo 的上游仓库（mobiuslabsgmbh/faster-whisper-large-v3-turbo）已私有化，
    按名字加载会联网并 401。本机缓存里已有 Systran/faster-whisper-large-v3 的完整快照，
    直接指向该目录即可离线加载，不触网、不会 401。
    """
    if os.path.isdir(model_name):
        return model_name
    repo = model_name if '/' in model_name else f'Systran/faster-whisper-{model_name}'
    cache_name = 'models--' + repo.replace('/', '--')
    for root in _HF_CACHE_ROOTS:
        if not root:
            continue
        snaps = os.path.join(root, 'hub', cache_name, 'snapshots')
        if not os.path.isdir(snaps):
            continue
        for name in sorted(os.listdir(snaps), reverse=True):
            path = os.path.join(snaps, name)
            if os.path.isfile(os.path.join(path, 'model.bin')):
                return path
    return model_name


def transcribe_audio(audio_path, model_name='large-v3', language='zh'):
    """用 faster-whisper 转写音频，返回文本。

    默认 large-v3：本机已有离线快照，走本地目录加载。首次换成未缓存的模型才会联网下载。
    """
    model_ref = resolve_model_dir(model_name)
    if model_ref == model_name:
        log(f'加载模型: {model_name}（本地未找到快照，将联网下载）')
    else:
        log(f'加载模型: {model_name}（本地快照 {model_ref}）')
    try:
        from faster_whisper import WhisperModel

        # CPU 模式：int8 量化，省内存
        model = WhisperModel(
            model_ref,
            device='cpu',
            compute_type='int8',
        )

        log(f'开始转写: {audio_path}')
        start_time = time.time()

        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,           # 过滤静音段
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
                threshold=0.5,
            ),
            initial_prompt='以下是简体中文的语音转写：',
            condition_on_previous_text=False,  # 避免重复输出
        )

        # 收集所有段文本
        texts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                texts.append(f'[{segment.start:.1f}s-{segment.end:.1f}s] {text}')

        elapsed = time.time() - start_time
        audio_duration = info.duration if info else 0
        log(f'转写完成: {len(texts)} 段, 音频 {audio_duration:.0f}s, 耗时 {elapsed:.0f}s'
            f'（速度: {audio_duration / elapsed:.1f}x 实时）' if elapsed > 0 and audio_duration > 0 else f'转写完成: {len(texts)} 段')

        return '\n'.join(texts), None

    except ImportError:
        return '', 'faster-whisper 未安装，执行: pip install faster-whisper'
    except Exception as e:
        return '', f'转写失败: {str(e)}'


def main():
    parser = argparse.ArgumentParser(description='视频 ASR 转写工具')
    parser.add_argument('url', nargs='?', help='视频 URL（使用 --input 指定本地文件时可省略）')
    parser.add_argument(
        '--input',
        help='本地音视频文件路径，跳过下载直接转写（用于已下载到本地的视频）',
    )
    parser.add_argument(
        '--model',
        default='large-v3',
        choices=['small', 'medium', 'large-v3', 'large-v3-turbo'],
        help='ASR 模型（默认 large-v3，本机有离线快照；small 最快但精度低；large-v3-turbo 上游仓库已私有化，按名字加载会 401，不建议）',
    )
    parser.add_argument(
        '--max-duration',
        type=int,
        default=30,
        help='最大视频时长（分钟），超过则跳过（默认 30）',
    )
    parser.add_argument(
        '--language',
        default='zh',
        help='语言代码（默认 zh，auto 为自动检测）',
    )

    args = parser.parse_args()

    # 检查磁盘空间（至少 2GB）
    try:
        import shutil
        free_bytes = shutil.disk_usage(tempfile.gettempdir()).free
        if free_bytes < 2 * 1024 * 1024 * 1024:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error',
                'error': f'磁盘空间不足: {free_bytes // (1024**3)}GB 可用，需至少 2GB',
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(1)
    except Exception:
        pass  # 空间检查失败不阻塞

    # 1. 准备音频（本地文件 或 下载）
    with tempfile.TemporaryDirectory() as tmpdir:
        if args.input:
            audio_path, error = prepare_audio_local(args.input, tmpdir)
        else:
            if not args.url:
                output = {
                    'success': False, 'text': '', 'char_count': 0,
                    'method': 'error',
                    'error': '需提供视频 URL 或 --input 本地文件路径',
                }
                print(json.dumps(output, ensure_ascii=False))
                sys.exit(1)
            audio_template = os.path.join(tmpdir, 'audio.%(ext)s')
            audio_path, error = download_audio(args.url, audio_template, args.max_duration)

        if error:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error', 'error': error,
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(1)

        log(f'音频下载完成: {audio_path}')

        # 2. ASR 转写
        language = args.language if args.language != 'auto' else None
        text, error = transcribe_audio(audio_path, args.model, language)

        if error:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error', 'error': error,
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(1)

        char_count = len(text.replace('\n', '').replace(' ', ''))
        method = f'faster-whisper-{args.model}'

        output = {
            'success': True,
            'text': text,
            'char_count': char_count,
            'method': method,
            'error': None,
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
