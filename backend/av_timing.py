"""Container/packet timing evidence, not content-level lip synchronization."""
import math

REVIEW_THRESHOLD_SECONDS = 0.25


def compare_tracks(video, audio):
    result = {"status": "unavailable", "video": video, "audio": audio,
              "start_offset_seconds": None, "end_offset_seconds": None,
              "duration_difference_seconds": None, "review_threshold_seconds": REVIEW_THRESHOLD_SECONDS,
              "lip_sync": "not_assessed"}
    if audio is None:
        result["status"] = "no_audio"
        return result
    values = [track.get(key) for track in (video, audio) for key in ("start_seconds", "duration_seconds")]
    if any(value is None or not math.isfinite(value) for value in values):
        return result
    if video["duration_seconds"] <= 0 or audio["duration_seconds"] <= 0:
        return result
    start = audio["start_seconds"] - video["start_seconds"]
    duration = audio["duration_seconds"] - video["duration_seconds"]
    end = start + duration
    result.update({"start_offset_seconds": round(start, 4), "end_offset_seconds": round(end, 4),
                   "duration_difference_seconds": round(duration, 4),
                   "status": "timing_difference" if max(abs(start), abs(end)) > REVIEW_THRESHOLD_SECONDS else "boundaries_aligned"})
    return result


def inspect_timing(container):
    video = container.streams.video[0]
    audio = container.streams.audio[0] if container.streams.audio else None
    streams = [stream for stream in (video, audio) if stream is not None]
    tracks = {}
    for stream in streams:
        start = float(stream.start_time * stream.time_base) if stream.start_time is not None else None
        duration = float(stream.duration * stream.time_base) if stream.duration is not None else None
        tracks[stream.index] = {"stream_index": stream.index, "start_seconds": start,
                                "duration_seconds": duration, "source": "stream_metadata"}
    # WebM commonly omits stream duration; estimate only from complete timestamped packets.
    if any(track["start_seconds"] is None or track["duration_seconds"] is None for track in tracks.values()):
        spans = {stream.index: [] for stream in streams}
        complete = True
        for index, packet in enumerate(container.demux(streams)):
            if index >= 30000:
                complete = False
                break
            if packet.pts is not None and packet.size:
                start = float(packet.pts * packet.time_base)
                end = start + float(packet.duration * packet.time_base) if packet.duration else None
                spans[packet.stream.index].append((start, end))
        if complete:
            for key, samples in spans.items():
                track = tracks[key]
                if samples and any(track[field] is None for field in ("start_seconds", "duration_seconds")):
                    if all(end is not None for _, end in samples):
                        start = track["start_seconds"] if track["start_seconds"] is not None else min(s[0] for s in samples)
                        end = max(s[1] for s in samples)
                        track.update({"start_seconds": start, "duration_seconds": end - start, "source": "packet_timestamps"})
    for track in tracks.values():
        for key in ("start_seconds", "duration_seconds"):
            value = track[key]
            track[key] = round(value, 6) if value is not None and math.isfinite(value) else None
    return compare_tracks(tracks[video.index], tracks[audio.index] if audio is not None else None)
