"""Assertions for the bounded PR19 build-tool qualification (no publishing)."""
import json
import os
import re
import sys


def verify_builder(name, driver, platforms, nodes):
    if not name or driver != 'docker-container':
        raise ValueError('expected a named docker-container builder')
    if 'linux/amd64' not in platforms.split(','):
        raise ValueError('builder must advertise linux/amd64')
    if not nodes or any(node.get('status') != 'running' for node in nodes):
        raise ValueError('builder nodes must be running')


def verify_image(image_id, digest, metadata, loaded_id):
    for value in (image_id, digest):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
            raise ValueError('missing or malformed build output digest')
    if image_id != loaded_id or metadata.get('containerimage.config.digest') != image_id:
        raise ValueError('loaded image does not match build action config digest')
    if metadata.get('containerimage.digest') != digest:
        raise ValueError('build action digest does not match metadata')


if __name__ == '__main__':
    if sys.argv[1] == 'builder':
        verify_builder(os.environ['BUILDER_NAME'], os.environ['BUILDER_DRIVER'],
                       os.environ['BUILDER_PLATFORMS'], json.loads(os.environ['BUILDER_NODES']))
    elif sys.argv[1] == 'image':
        verify_image(os.environ['IMAGE_ID'], os.environ['IMAGE_DIGEST'],
                     json.loads(os.environ['IMAGE_METADATA']), os.environ['LOADED_ID'])
    else:
        raise SystemExit('expected builder or image')
