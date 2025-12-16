#!/usr/bin/env python3
"""
TaskForge CLI

Usage:
    taskforge capture "task name"     # Start recording
    taskforge process ./recording/    # Generate playbook from recording  
    taskforge devices                 # List available cameras
    taskforge config --camera oak-d   # Set default camera
"""

import sys
import signal
from pathlib import Path
import click


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """🎥→📋 Watch me work. Write the manual."""
    pass


@cli.command()
@click.argument('task_name')
@click.option('--camera', '-c', type=click.Choice(['oak-d-s2', 'oak-d-pro', 'realsense-d455', 'webcam', 'auto']),
              default='auto', help='Camera to use (webcam for sensor-blind mode)')
@click.option('--fps', default=None, type=int, help='Frames per second (auto-detected if not set)')
@click.option('--output', '-o', type=click.Path(), default='./recordings', help='Output directory')
@click.option('--no-video', is_flag=True, help='Skip video compilation')
@click.option('--no-depth', is_flag=True, help='Force sensor-blind mode (webcam only, no depth)')
def capture(task_name: str, camera: str, fps: int, output: str, no_video: bool, no_depth: bool):
    """Start a capture session for a task.

    Use --webcam or --no-depth for mobile devices without depth cameras.
    """
    from .cameras import CameraType
    from .capture import TaskCapture, CaptureConfig

    # Map camera choice to type
    camera_map = {
        'oak-d-s2': CameraType.OAK_D_S2,
        'oak-d-pro': CameraType.OAK_D_PRO,
        'realsense-d455': CameraType.REALSENSE_D455,
        'webcam': CameraType.WEBCAM,
        'auto': None
    }

    # Force webcam if --no-depth specified
    if no_depth:
        camera_type = CameraType.WEBCAM
    else:
        camera_type = camera_map[camera]

    config = CaptureConfig(
        fps=fps,
        save_video=not no_video,
        # Disable depth saving in sensor-blind mode
        save_depth_raw=camera_type != CameraType.WEBCAM,
        save_depth_viz=camera_type != CameraType.WEBCAM,
    )

    capture_session = TaskCapture(
        task_name=task_name,
        output_base=Path(output),
        camera_type=camera_type,
        config=config
    )
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n")
        capture_session.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        capture_session.start()
        
        # Wait for user to stop
        click.echo("\n" + "="*50)
        click.echo("🎬 RECORDING")
        click.echo("   Narrate what you're doing!")
        click.echo("   Press Ctrl+C to stop and process")
        click.echo("="*50 + "\n")
        
        # Keep running until interrupted
        signal.pause()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('recording_dir', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default='./playbooks', help='Output directory')
@click.option('--whisper-model', default='base', 
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large']),
              help='Whisper model size')
def process(recording_dir: str, output: str, whisper_model: str):
    """Process a recording into a playbook."""
    from .process import TaskProcessor
    
    try:
        processor = TaskProcessor(
            recording_dir=Path(recording_dir),
            output_base=Path(output),
            whisper_model=whisper_model
        )
        playbook = processor.process()
        
        click.echo(f"\n✅ Generated playbook: {playbook.title}")
        click.echo(f"   Steps: {len(playbook.steps)}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def devices():
    """List available depth cameras."""
    from .cameras import list_cameras
    
    cameras = list_cameras()
    
    if not cameras:
        click.echo("No supported depth cameras found.")
        click.echo("\nSupported cameras:")
        click.echo("  - Luxonis OAK-D S2 / Pro / Pro W")
        click.echo("  - Intel RealSense D435 / D455")
        return
    
    click.echo(f"Found {len(cameras)} camera(s):\n")
    
    for cam in cameras:
        click.echo(f"  [{cam['type'].upper()}]")
        click.echo(f"    ID: {cam['id']}")
        if 'name' in cam:
            click.echo(f"    Name: {cam['name']}")
        if 'state' in cam:
            click.echo(f"    State: {cam['state']}")
        click.echo()


@cli.command()
@click.option('--camera', type=click.Choice(['oak-d-s2', 'oak-d-pro', 'realsense-d455']),
              help='Set default camera')
@click.option('--show', is_flag=True, help='Show current config')
def config(camera: str, show: bool):
    """Configure TaskForge settings."""
    import json
    
    config_path = Path.home() / '.taskforge' / 'config.json'
    
    if show or (not camera):
        if config_path.exists():
            with open(config_path) as f:
                cfg = json.load(f)
            click.echo("Current configuration:")
            click.echo(json.dumps(cfg, indent=2))
        else:
            click.echo("No configuration file found. Using defaults.")
        return
    
    # Update config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    cfg = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
    
    if camera:
        cfg['default_camera'] = camera
        click.echo(f"Default camera set to: {camera}")
    
    with open(config_path, 'w') as f:
        json.dump(cfg, f, indent=2)


@cli.command()
def platform():
    """Show detected platform and recommended settings."""
    from .platform import print_platform_info
    print_platform_info()


@cli.command()
@click.argument('recording_dir', type=click.Path(exists=True))
def preview(recording_dir: str):
    """Preview a recording's keyframes."""
    import json
    import cv2
    
    recording_path = Path(recording_dir)
    metadata_path = recording_path / "metadata.json"
    
    if not metadata_path.exists():
        click.echo("Error: No metadata.json found", err=True)
        sys.exit(1)
    
    with open(metadata_path) as f:
        metadata = json.load(f)
    
    keyframes = [f for f in metadata['frames'] if f.get('is_keyframe', False)]
    
    click.echo(f"Recording: {metadata['session']['name']}")
    click.echo(f"Duration: {metadata['session']['duration_seconds']:.1f}s")
    click.echo(f"Total frames: {metadata['session']['frames_captured']}")
    click.echo(f"Keyframes: {len(keyframes)}")
    click.echo("\nPress any key to advance, 'q' to quit\n")
    
    for i, frame in enumerate(keyframes):
        img_path = recording_path / "frames" / frame['rgb_file']
        if not img_path.exists():
            continue
        
        img = cv2.imread(str(img_path))
        
        # Add overlay
        cv2.putText(img, f"Frame {i+1}/{len(keyframes)} @ {frame['relative_time']:.1f}s",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        cv2.imshow('TaskForge Preview', img)
        
        key = cv2.waitKey(0) & 0xFF
        if key == ord('q'):
            break
    
    cv2.destroyAllWindows()


@cli.command()
@click.argument('task_description')
def briefing(task_description: str):
    """Get a briefing before starting a task (searches memory for related playbooks)."""
    try:
        from .memory import get_task_briefing, get_memory_client

        client = get_memory_client()
        if not client.is_available():
            click.echo("Memory service not available.")
            click.echo("Set MEMORABLE_URL environment variable or start memoRable service.")
            return

        brief = get_task_briefing(task_description)

        if not brief:
            click.echo(f"No related playbooks found for: {task_description}")
            click.echo("This might be a new type of task!")
            return

        click.echo("\n" + "=" * 50)
        click.echo(f"📋 TASK BRIEFING: {task_description}")
        click.echo("=" * 50)

        click.echo(f"\n{brief['tip']}\n")

        if brief['related_playbooks']:
            click.echo("Related playbooks:")
            for pb in brief['related_playbooks']:
                click.echo(f"  • {pb['title']} (salience: {pb['salience']})")
                if pb['path']:
                    click.echo(f"    └─ {pb['path']}")

        if brief['suggested_tools']:
            click.echo(f"\nTools you might need:")
            for tool in brief['suggested_tools'][:5]:
                click.echo(f"  • {tool}")

        if brief['suggested_parts']:
            click.echo(f"\nParts commonly used:")
            for part in brief['suggested_parts'][:5]:
                click.echo(f"  • {part}")

        click.echo()

    except ImportError:
        click.echo("Memory integration requires: pip install httpx")
    except Exception as e:
        click.echo(f"Error getting briefing: {e}", err=True)


@cli.command()
@click.argument('query')
@click.option('--limit', '-n', default=5, help='Max results to show')
def recall(query: str, limit: int):
    """Search for past playbooks by topic or description."""
    try:
        from .memory import search_related_playbooks, get_memory_client

        client = get_memory_client()
        if not client.is_available():
            click.echo("Memory service not available.")
            click.echo("Set MEMORABLE_URL environment variable or start memoRable service.")
            return

        results = search_related_playbooks(query, limit=limit)

        if not results:
            click.echo(f"No playbooks found matching: {query}")
            return

        click.echo(f"\nFound {len(results)} playbook(s) matching '{query}':\n")

        for i, result in enumerate(results, 1):
            pb = result.playbook_data or {}
            click.echo(f"{i}. {pb.get('title', 'Unknown')} [salience: {result.salience_score}]")
            if pb.get('summary'):
                click.echo(f"   {pb['summary'][:80]}...")
            if result.topics:
                click.echo(f"   Topics: {', '.join(result.topics[:5])}")
            if pb.get('playbook_path'):
                click.echo(f"   Path: {pb['playbook_path']}")
            click.echo()

    except ImportError:
        click.echo("Memory integration requires: pip install httpx")
    except Exception as e:
        click.echo(f"Error searching: {e}", err=True)


def main():
    cli()


if __name__ == '__main__':
    main()
