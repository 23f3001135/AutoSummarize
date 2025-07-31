try:
        (
            ffmpeg
            .input(input_video)
            .output(
                f"output_%03d.mp4",  # Output filename pattern (e.g., output_001.mp4)
                segment_time=segment_duration,
                f="segment",
                c="copy"  # Copy streams without re-encoding for speed
            )
            .run(overwrite_output=True)
        )
        print(f"Video '{input_video}' split into {segment_duration}-second chunks.")
    except ffmpeg.Error as e:
        print(f"Error: {e.stderr.decode()}")