from subprocess import run, PIPE, STDOUT


def search_available_usbcam() -> list[int]:
    results = run(['bash', '-c', "v4l2-ctl --list-devices | awk '/Camera|FX3/{getline; print $1}'"], 
        stdout=PIPE, 
        stderr=STDOUT
    ).stdout.decode().split('\n')
    return [
        int(dev.removeprefix('/dev/video')) 
            for dev in results if dev.startswith('/dev/video')
    ]
