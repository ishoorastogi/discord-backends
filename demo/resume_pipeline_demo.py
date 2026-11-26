#!/usr/bin/env python3
"""Upload a temporary PDF through the real service; observe results in memory.

Default: real MiniLM, local files only. --mock-model is a separate, explicit
fallback demo; it cannot verify real model inference. No result files are saved.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
from importlib import import_module, util
import json
import os
from pathlib import Path
import queue
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
STAGES = ['RESUME_UPLOAD', 'PARSE', 'EXTRACTION', 'NORMALIZATION', 'VECTORIZATION', 'RESUME_WRITE']


def make_pdf(path: Path) -> None:
    """Create a text PDF using the parser's existing pypdf dependency."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    lines = Path(__file__).with_name('synthetic_resume.txt').read_text().splitlines()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    fonts = DictionaryObject()
    for name, face in [('F1', 'Helvetica'), ('F2', 'Helvetica-Bold')]:
        fonts[NameObject('/' + name)] = writer._add_object(DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/' + face),
        }))
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): fonts})
    commands = ['1 1 1 rg 0 0 612 792 re f 0 0 0 rg']
    y = 744
    for i, line in enumerate(lines):
        bold = i == 0 or line in {'EDUCATION', 'SKILLS', 'EXPERIENCE', 'PROJECTS'}
        size = 18 if i == 0 else 11
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        commands.append(f'BT /{"F2" if bold else "F1"} {size} Tf 48 {y} Td ({escaped}) Tj ET')
        y -= 22 if i == 0 else 19
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(commands).encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)
    text = PdfReader(path).pages[0].extract_text()
    if not all(line in text for line in lines if line):
        raise RuntimeError('Generated PDF failed text round-trip validation')


def run(args) -> int:
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if branch not in {'feature/resume-pipeline-integration', 'feature/addu-resume-integration'}:
        raise RuntimeError(f'Wrong branch: {branch}; no branches will be switched')
    needed = ['numpy', 'pypdf', 'dotenv']
    if not args.mock_model:
        needed += ['sentence_transformers', 'torch']
    missing = [name for name in needed if util.find_spec(name) is None]
    if missing:
        raise RuntimeError(f'Missing modules: {", ".join(missing)}. Install with:\n'
                           '.venv/bin/python -m pip install -r requirements.txt\n'
                           '.venv/bin/python -m pip install -e "internships/resume-pipeline/resume-parser[dev]" '
                           '-e "internships/resume-pipeline/extraction[dev]"')

    # Set before importing Hugging Face or the production entry point. No downloads,
    # file logging, ESCO caches, or bytecode are needed for this dictionary-mode demo.
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      LOG_FILE='', LOG_LEVEL='WARNING',
                      SHUTDOWN_TIMEOUT_SECONDS='10', TOKENIZERS_PARALLELISM='false')
    sys.dont_write_bytecode = True
    import numpy as np

    sys.path.insert(0, str(ROOT))
    from internships.src import config

    load_settings = config.load_settings
    application = runpy.run_path(str(ROOT / 'internships/src/main.py'), run_name='demo_entrypoint')
    router_module = import_module('event_router')
    listener = import_module('tcp_listener')
    vectorizer = import_module('vectorization.resume_vectorizer')
    writer_handler = import_module('writer-handler')
    vector_columns = import_module('shared.db-utils.crud.resume_queries').VECTOR_COLUMNS
    writer_events = queue.Queue(1)
    request_id = 'demo-' + uuid.uuid4().hex
    discord_id = '123456789012345678'
    state = {'stages': [], 'snapshots': {}, 'errors': [], 'connected': False, 'accepted': False}
    ready, completed = threading.Event(), threading.Event()
    route = router_module.EventRouter.route
    create_server = listener.create_server

    def observe(router, event):
        # Delegate to the real router/handler. Observation never produces an event,
        # invokes a handler directly, or replaces a queue or result.
        if event.get('request_id') != request_id:
            return route(router, event)
        stage = event.get('event')
        state['stages'].append(stage)
        try:
            # PARSE creates a new event/data dictionary. Its real output first
            # becomes observable as the input to queued EXTRACTION.
            if stage == 'EXTRACTION':
                resume = event.get('data', {}).get('resume')
                if resume is None or not resume.raw_text.strip():
                    raise RuntimeError('PARSE produced no resume text')
                state['resume'] = resume
                state['snapshots']['PARSE'] = resume.raw_text
            route(router, event)
            data = event.get('data', {})
            if data.get('discord_id') != discord_id:
                raise RuntimeError('Discord ID changed')
            if stage in ('EXTRACTION', 'NORMALIZATION', 'VECTORIZATION'):
                if data.get('resume') is not state.get('resume'):
                    raise RuntimeError('Original Resume object was replaced')
                if stage == 'EXTRACTION':
                    snapshot = data['resume'].to_dict()
                    if not any(snapshot['skills'].values()):
                        raise RuntimeError('EXTRACTION produced no skills')
                    expected_skills = {'Python', 'JS', 'SQL', 'Flask', 'Postgres'}
                    actual_skills = {skill for group in snapshot['skills'].values() for skill in group}
                    if not expected_skills <= actual_skills:
                        raise RuntimeError('Expected extracted skills missing')
                    if not any(e['degree'] == 'BS in Computer Science' for e in snapshot['education']):
                        raise RuntimeError('Expected education missing')
                    if not any('Backend Developer' in (e['title'] or '') for e in snapshot['experience']):
                        raise RuntimeError('Expected experience missing')
                    if {p['name'] for p in snapshot['projects']} != {'REST API', 'Web Application'}:
                        raise RuntimeError('Expected projects missing')
                    state['snapshots'][stage] = deepcopy(snapshot)
                elif stage == 'NORMALIZATION':
                    normalized = data.get('normalized_resume')
                    if not isinstance(normalized, dict) or not normalized.get('skills'):
                        raise RuntimeError('NORMALIZATION produced no normalized skills')
                    if not {'python', 'javascript', 'sql', 'flask', 'postgresql'} <= set(normalized['skills']):
                        raise RuntimeError('Expected normalized aliases missing')
                    state['snapshots'][stage] = deepcopy(normalized)
        except Exception as error:
            state['errors'].append(f'{stage}: {type(error).__name__}: {error}')
            completed.set()
            raise

    def capture_completion(event):
        if (event.get('event') != 'RESUME_WRITE'
                or event.get('request_id') != request_id):
            raise RuntimeError('Invalid completion envelope')
        data = event['data']
        if data.get('discord_id') != discord_id or data.get('resume') is not state.get('resume'):
            raise RuntimeError('Completion metadata or Resume identity changed')
        resume = data['resume']
        if resume.overall_vector is None:
            raise RuntimeError('VECTORIZATION produced no usable result')
        vectors = {}
        for name in vector_columns:
            value = getattr(resume, name)
            if value is None:
                continue
            vector = np.asarray(value, dtype=np.float32)
            if (vector.shape != (384,) or not np.isfinite(vector).all()
                    or not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)):
                raise RuntimeError(f'Invalid embedding: {name}')
            vectors[name] = vector
        if data['normalized_resume'] != state['snapshots']['NORMALIZATION']:
            raise RuntimeError('Normalized data changed during vectorization')
        extracted = state['snapshots']['EXTRACTION']
        if any(value != extracted[key] for key, value in resume.to_dict().items() if key not in vector_columns):
            raise RuntimeError('Extracted Resume changed after extraction')
        state['snapshots']['VECTORIZATION'] = vectors
        state['final_keys'] = sorted(data)
        completed.set()

    def bind_demo_server(host, port, intake_queue):
        # Keep the real TCP server and its intake queue; override only the address
        # in memory so the demo cannot collide with the configured production port.
        server = create_server('127.0.0.1', 0, intake_queue)
        state['server'] = server
        ready.set()
        return server

    with tempfile.TemporaryDirectory(prefix='resume-pipeline-demo-') as temporary:
        pdf_path = Path(temporary) / 'synthetic_resume.pdf'
        make_pdf(pdf_path)
        event = {'event': 'RESUME_UPLOAD', 'request_id': request_id, 'data': {
            'discord_id': discord_id, 'filename': pdf_path.name, 'content_type': 'application/pdf',
            'pdf_base64': base64.b64encode(pdf_path.read_bytes()).decode('ascii')}}

        def upload():
            try:
                if not ready.wait(10):
                    raise RuntimeError('Service did not create a TCP listener')
                with socket.create_connection(state['server'].server_address, timeout=10) as connection:
                    state['connected'] = True
                    connection.sendall((json.dumps(event) + '\n').encode())
                    with connection.makefile('rb') as response:
                        ack = json.loads(response.readline(65536))
                    state['accepted'] = (ack.get('event') == 'UPLOAD_ACCEPTED'
                                         and ack.get('request_id') == request_id)
                    if not state['accepted']:
                        raise RuntimeError(f'Upload not accepted: {ack}')
                    capture_completion(writer_events.get(timeout=args.timeout))
            except Exception as error:
                state['errors'].append(f'Client: {type(error).__name__}: {error}')
            finally:
                if 'server' in state:
                    state['server'].shutdown()

        class MockModel:
            def encode(self, texts, **kwargs):
                vectors = []
                for text in texts:
                    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], 'big')
                    vector = np.random.default_rng(seed).normal(size=384).astype(np.float32)
                    vectors.append(vector / np.linalg.norm(vector))
                return np.asarray(vectors, dtype=np.float32)

        from contextlib import ExitStack
        client = threading.Thread(target=upload, name='demo-tcp-client', daemon=True)
        with ExitStack() as instrumentation:
            instrumentation.enter_context(patch.object(
                config, 'load_settings', lambda: replace(load_settings(), esco_csv=None, esco_cache_dir=None),
            ))
            instrumentation.enter_context(patch.object(router_module.EventRouter, 'route', observe))
            instrumentation.enter_context(patch.object(listener, 'create_server', bind_demo_server))
            instrumentation.enter_context(patch.object(
                writer_handler, 'handle_resume_write',
                lambda event, *, db_runtime: writer_events.put_nowait(event)
                if event.get('request_id') == request_id else None,
            ))
            if args.mock_model:
                instrumentation.enter_context(patch.object(vectorizer, '_model', MockModel()))
            client.start()
            try:
                application['main']()
            finally:
                client.join(timeout=12)
        if client.is_alive():
            state['errors'].append('Client did not finish')

    print('=== RESUME PIPELINE DEMO ===')
    print('INFERENCE: ' + ('MOCKED embeddings; real MiniLM inference NOT VERIFIED'
                            if args.mock_model else 'REAL MiniLM; cached files only; no mocked results'))
    print('NORMALIZATION: dictionary-only (ESCO disabled for this demo)')
    print(f'REQUEST ID: {request_id}')
    checks = [('TCP connection established', state['connected']),
              ('Resume upload accepted', state['accepted'])]
    checks += [(label, stage in state['snapshots']) for stage, label in [
        ('PARSE', 'PDF parsing completed'), ('EXTRACTION', 'Structured extraction completed'),
        ('NORMALIZATION', 'Normalization completed'), ('VECTORIZATION', 'Vectorization completed')]]
    checks.append(('Writer queue received RESUME_WRITE', 'VECTORIZATION' in state['snapshots']))
    checks.append(('Stages executed exactly once in order', state['stages'] == STAGES))
    for label, passed in checks:
        print(f'[{"PASS" if passed else "FAIL"}] {label}')
    print('OBSERVED STAGES: ' + ' -> '.join(state['stages']))
    extracted = state['snapshots'].get('EXTRACTION')
    if extracted:
        print('\nEXTRACTED SKILLS:')
        print(json.dumps(extracted['skills'], indent=2))
        print('\nEXTRACTED STRUCTURED FIELDS:')
        print(json.dumps({key: extracted[key] for key in ('education', 'experience', 'projects')}, indent=2))
    if 'NORMALIZATION' in state['snapshots']:
        normalized = state['snapshots']['NORMALIZATION']
        print('\nNORMALIZED SKILLS:\n' + ', '.join(normalized['skills']))
        print('\nNORMALIZED OUTPUT:\n' + json.dumps(normalized, indent=2))
    if 'VECTORIZATION' in state['snapshots']:
        print('\nVECTOR RESULTS:')
        for name, vector in state['snapshots']['VECTORIZATION'].items():
            print(f'{name}: shape={vector.shape}, dtype={vector.dtype}, '
                  f'norm={np.linalg.norm(vector):.6f}, finite={bool(np.isfinite(vector).all())}')
        print('\nFINAL EVENT DATA KEYS: ' + ', '.join(state['final_keys']))
        print('[PASS] Request/Discord IDs, original Resume and normalized data preserved')
    for error in state['errors']:
        print('[FAIL] ' + error)
    print('Temporary PDF removed. The demo captured the write event in memory.')
    return 0 if all(passed for _, passed in checks) and not state['errors'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=180, help='Maximum inference wait in seconds')
    parser.add_argument('--mock-model', action='store_true', help='Explicit separate demo using MOCKED embeddings')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        sys.exit(run(args))
    except Exception as error:
        print(f'[FAIL] {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
