"""Exercise imported algorithms with a deterministic offline model."""
from copy import deepcopy
from functools import partial
from importlib import import_module
import json
from pathlib import Path
import queue
import sys
from unittest.mock import Mock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'internships/event-managers/handler',
                  ROOT / 'internships/event-managers/router', ROOT / 'internships/event-listener'):
    sys.path.insert(0, str(directory))

from models import Resume, Education, Experience, Project, Skills
from normalization_adapter import normalization_input
import model_resources
from normalization.normalize_resume import make_normalizer
from normalization import esco_skills
from vectorization import resume_vectorizer as vectorizer
from shared import event_queue
from event_router import EventRouter

handler = import_module('resume-handler')
VECTOR_COLUMNS = import_module('shared.db-utils.crud.resume_queries').VECTOR_COLUMNS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    model_resources.get_normalizer.cache_clear()
    model = Mock()
    model.encode.side_effect = lambda texts, **kwargs: np.tile(
        np.full(384, 1 / np.sqrt(384), dtype=np.float32), (len(texts), 1))
    monkeypatch.setattr(vectorizer, '_model', model)
    yield model
    model_resources.get_normalizer.cache_clear()


def event(resume=None):
    return {'event': 'NORMALIZATION', 'request_id': 'abc', 'data': {
        'discord_id': '123', 'filename': 'resume.pdf',
        'resume': resume if resume is not None else Resume('text', skills=Skills(languages=['JS']))}}


def test_adapter_and_handoff_preserve_data(offline):
    resume = Resume('text', education=[Education('School', 'BS', '2025')],
                    projects=[Project('API', skills=['Postgres'])],
                    experience=[Experience('Engineer')], skills=Skills(languages=['JS']))
    before = deepcopy(resume.to_dict())
    adapted = normalization_input(resume)
    assert adapted['skills'] == before['skills']
    assert adapted['education'] == before['education']
    assert 'field' not in adapted['education'][0]
    assert 'bullets' not in adapted['experience'][0]
    pending = queue.Queue()
    original = event(resume)
    handler.handle_normalization(original, resume_queue=pending)
    result = pending.get_nowait()
    assert result['event'] == 'VECTORIZATION'
    assert result['request_id'] == 'abc'
    assert result['data'] is original['data']
    assert result['data']['normalized_resume']['skills'] == ['javascript']
    assert result['data']['normalized_resume']['projects'][0]['skills'] == ['postgresql']
    normalized = result['data']['normalized_resume']
    snapshot = deepcopy(normalized)
    # Give each section its own unit vector so swapped fields fail the check.
    offline.encode.side_effect = [np.eye(6, 384, dtype=np.float32)[[i]] for i in range(6)]
    writer_queue = queue.Queue()
    handler.handle_vectorization(result, writer_queue=writer_queue)
    completed = writer_queue.get_nowait()
    assert completed['event'] == 'RESUME_WRITE'
    assert completed['request_id'] == 'abc'
    assert completed['data'] is result['data']
    assert result['data']['normalized_resume'] is normalized
    assert normalized == snapshot
    assert result['data']['resume'] is resume
    serialized = json.loads(json.dumps(resume.to_dict()))
    assert 'resume_vectors' not in completed['data']
    for i, field_name in enumerate(VECTOR_COLUMNS):
        assert serialized.pop(field_name) == np.eye(6, 384)[i].tolist()
        assert before.pop(field_name) is None
    assert serialized == before
    assert pending.empty()


def test_optional_fields_and_empty_resume(offline):
    original = event(Resume(''))
    pending = queue.Queue()
    handler.handle_normalization(original, resume_queue=pending)
    result = pending.get_nowait()
    writer_queue = queue.Queue()
    handler.handle_vectorization(result, writer_queue=writer_queue)
    assert writer_queue.empty()
    assert all(getattr(result['data']['resume'], column) is None for column in VECTOR_COLUMNS)
    offline.encode.assert_not_called()


@pytest.mark.parametrize('data', [None, [], {}, {'discord_id': 'bad', 'resume': Resume('')},
                                      {'discord_id': '123', 'resume': {}}])
def test_invalid_payloads(data):
    pending = queue.Queue()
    handler.handle_normalization({'data': data}, resume_queue=pending)
    handler.handle_vectorization({'data': data}, writer_queue=pending)
    assert pending.empty()


def test_full_queue(monkeypatch):
    model_resources.get_normalizer(None, None)
    pending = queue.Queue(1)
    pending.put('existing')
    logger = Mock()
    monkeypatch.setattr(handler, 'logger', logger)
    handler.handle_normalization(event(), resume_queue=pending)
    assert pending.get_nowait() == 'existing'
    assert pending.empty()
    logger.info.assert_called_once_with('Handling NORMALIZATION event')


def test_configured_esco_failure_is_not_fallback(tmp_path):
    missing_csv = tmp_path / 'missing.csv'
    with pytest.raises(OSError):
        make_normalizer(missing_csv)
    pending = queue.Queue()
    original = event()
    handler.handle_normalization(original, resume_queue=pending, esco_csv=missing_csv)
    assert pending.empty()
    assert 'normalized_resume' not in original['data']


def test_normalizer_reused():
    assert model_resources.get_normalizer() is model_resources.get_normalizer()


@pytest.mark.parametrize('invalid', [np.zeros(384, dtype=np.float32), np.ones(12, dtype=np.float32),
                                     np.full(384, np.nan, dtype=np.float32), None])
def test_invalid_vectors_not_published(monkeypatch, invalid):
    original = event()
    original['data']['normalized_resume'] = {'skills': ['python']}
    monkeypatch.setattr(vectorizer, 'vectorize_resume', lambda data: {'overall_vector': invalid} if invalid is not None else {})
    writer_queue = queue.Queue()
    handler.handle_vectorization(original, writer_queue=writer_queue)
    assert writer_queue.empty()
    assert original['data']['resume'].overall_vector is None


def test_vectorizer_receives_original_normalized_dict(monkeypatch):
    original = event()
    normalized = {'skills': ['python']}
    original['data']['normalized_resume'] = normalized
    mock = Mock(side_effect=RuntimeError('model failed'))
    monkeypatch.setattr(vectorizer, 'vectorize_resume', mock)
    writer_queue = queue.Queue()
    handler.handle_vectorization(original, writer_queue=writer_queue)
    assert mock.call_args.args[0] is normalized
    assert writer_queue.empty()


def test_real_worker_pipeline_dispatches_once(monkeypatch):
    # Match main's shared registry/router wiring, including the intake worker.
    intake = import_module('intake-handler')
    intake_queue, resume_queue = queue.Queue(), queue.Queue()
    router = EventRouter()
    intake.register_handlers(router, resume_queue=resume_queue, internship_queue=queue.Queue())
    writer_queue = queue.Queue()
    handler.register_handlers(router, resume_queue=resume_queue, writer_queue=writer_queue)
    stages = []
    for name, function in list(router._handlers.items()):
        def record(event, name=name, function=function):
            stages.append(name)
            function(event)
        router.register(name, record)
    resume = Resume('SKILLS\nProgramming Languages: Python\nPROJECTS\nAPI | Python')
    monkeypatch.setattr(handler, 'parse_resume_base64', lambda _: resume)
    registry = event_queue.HandlerRegistry()
    registry.register(partial(intake.process_event, router=router))
    workers = [event_queue.Worker(intake_queue, registry), event_queue.Worker(resume_queue, registry)]
    original = {'event': 'RESUME_UPLOAD', 'request_id': 'abc',
                'data': {'discord_id': '123', 'pdf_base64': 'mock'}}
    for worker in workers:
        worker.start()
    try:
        intake_queue.put(original)
        assert event_queue.drain(intake_queue, 3) == 0
        assert event_queue.drain(resume_queue, 3) == 0
        assert stages == ['RESUME_UPLOAD', 'PARSE', 'EXTRACTION', 'NORMALIZATION', 'VECTORIZATION']
        assert resume.skills.languages == ['Python']
        final = writer_queue.get_nowait()
        assert final['event'] == 'RESUME_WRITE'
        assert final['request_id'] == 'abc'
        assert final['data']['resume'] is resume
        assert set(final['data']) >= {'resume', 'normalized_resume'}
        assert final['data']['resume'].overall_vector is not None
    finally:
        assert event_queue.stop_workers(intake_queue, workers[:1], 3) == 0
        assert event_queue.stop_workers(resume_queue, workers[1:], 3) == 0


def test_semantic_layer_remains_available():
    from normalization.skill_normalizer import SkillNormalizer
    from normalization.normalize_resume import normalize_resume
    extractor = esco_skills.EscoSkillExtractor(
        skills=[{'label': 'Special skill', 'uri': 'urn:skill'}], cache_dir=None,
        embed_fn=lambda texts: np.ones((len(texts), 1), dtype=np.float32))
    normalized = normalize_resume({'skills': ['unknown phrase']}, SkillNormalizer(extractor=extractor))
    assert normalized['skills'] == ['Special skill']


def test_minilm_loaded_once(monkeypatch):
    import types
    factory = Mock()
    monkeypatch.setitem(sys.modules, 'sentence_transformers', types.SimpleNamespace(SentenceTransformer=factory))
    monkeypatch.setattr(vectorizer, '_model', None)
    first = vectorizer.get_model()
    assert vectorizer.get_model() is first
    factory.assert_called_once_with(vectorizer.MODEL_NAME)


def test_main_workers_run_complete_pipeline(monkeypatch, tmp_path):
    from internships.src import main
    tcp_listener = import_module('tcp_listener')
    config = main.config
    monkeypatch.setattr(config, 'load_environment', lambda: None)
    monkeypatch.setattr(config, '__file__', str(tmp_path / 'config.py'))
    monkeypatch.setenv('ESCO_CSV', str(tmp_path / 'missing.csv'))
    monkeypatch.setenv('ESCO_CACHE_DIR', str(tmp_path / 'legacy-cache'))
    (tmp_path / 'config.json').write_text(json.dumps({
        'TCP_HOST': '127.0.0.1', 'TCP_PORT': 12345,
        'ESCO_CSV': 'skills_en.csv', 'ESCO_CACHE_DIR': 'configured-cache',
    }), encoding='utf-8')
    (tmp_path / 'skills_en.csv').write_text(
        'preferredLabel,conceptUri\nPython (computer programming),urn:python\n', encoding='utf-8',
    )
    monkeypatch.setattr(esco_skills.EscoSkillExtractor, '_embed',
                        lambda self, texts: np.ones((len(texts), 1), dtype=np.float32))
    monkeypatch.setattr(main.signal, 'signal', lambda *args: None)
    resume = Resume('SKILLS\nProgramming Languages: Python, sample skill alias')
    monkeypatch.setattr(handler, 'parse_resume_base64', lambda _: resume)
    completed = []
    def capture(event, *, db_runtime):
        completed.append(event)

    monkeypatch.setattr(import_module('writer-handler'), 'handle_resume_write', capture)
    server = Mock()

    def create_server(host, port, intake_queue):
        server.serve_forever.side_effect = lambda: intake_queue.put({
            'event': 'RESUME_UPLOAD', 'request_id': 'main-test',
            'data': {'discord_id': '123', 'pdf_base64': 'mock'}})
        return server

    monkeypatch.setattr(tcp_listener, 'create_server', create_server)
    monkeypatch.setattr(tcp_listener, 'close_clients', lambda *args: 0)
    main.main()
    assert len(completed) == 1
    assert completed[0]['request_id'] == 'main-test'
    assert completed[0]['data']['resume'] is resume
    assert completed[0]['event'] == 'RESUME_WRITE'
    assert set(completed[0]['data']) >= {'resume', 'normalized_resume'}
    assert resume.overall_vector is not None
    assert completed[0]['data']['normalized_resume']['skills'] == ['Python (computer programming)']
    assert len(list((tmp_path / 'configured-cache').glob('esco_vectors_*.npy'))) == 1
    assert not (tmp_path / 'legacy-cache').exists()
    server.server_close.assert_called_once()


def test_completion_survives_subsequent_worker_events():
    from functools import partial
    results = queue.Queue(2)
    pending = event_queue.create_queue(4)
    router = EventRouter()
    handler.register_handlers(router, resume_queue=pending, writer_queue=results)
    router.register('NEXT', lambda event: None)
    registry = event_queue.HandlerRegistry()
    registry.register(router.route)
    worker = event_queue.Worker(pending, registry)
    resumes = [Resume('first'), Resume('second')]
    worker.start()
    try:
        for i, resume in enumerate(resumes):
            pending.put({'event': 'VECTORIZATION', 'request_id': str(i), 'source': 'test',
                         'data': {'discord_id': '123', 'resume': resume,
                                  'normalized_resume': {'skills': ['python']}}})
        pending.put({'event': 'NEXT'})
        assert event_queue.drain(pending, 3) == 0
        assert results.qsize() == 2
        for i, resume in enumerate(resumes):
            result = results.get_nowait()
            assert result['event'] == 'RESUME_WRITE'
            assert result['request_id'] == str(i)
            assert result['source'] == 'test'
            assert result['data']['discord_id'] == '123'
            assert result['data']['resume'] is resume
            assert result['data']['normalized_resume'] == {'skills': ['python']}
            assert len(resume.overall_vector) == len(resume.skills_vector) == 384
            assert resume.titles_vector is resume.experience_vector is resume.projects_vector is resume.education_vector is None
            results.task_done()
    finally:
        assert event_queue.stop_workers(pending, [worker], 3) == 0


def test_full_completion_queue_does_not_report_delivery(monkeypatch):
    results = queue.Queue(1)
    results.put('existing')
    original = event()
    original['data']['normalized_resume'] = {'skills': ['python']}
    logger = Mock()
    monkeypatch.setattr(handler, 'logger', logger)
    handler.handle_vectorization(original, writer_queue=results)
    assert results.get_nowait() == 'existing'
    assert results.empty()
    logger.info.assert_called_once_with('Handling VECTORIZATION event')
    logger.warning.assert_called_once()


def test_distinct_vectors_average_and_renormalize(monkeypatch):
    def embed(texts):
        vectors = np.zeros((len(texts), 384), dtype=np.float32)
        for i in range(len(texts)):
            vectors[i, i] = 1
        return vectors
    monkeypatch.setattr(vectorizer, 'embed_texts', embed)
    vectors = vectorizer.vectorize_resume({'projects': [{'name': 'One'}, {'name': 'Two'}]})
    expected = np.zeros(384, dtype=np.float32)
    expected[:2] = 1 / np.sqrt(2)
    np.testing.assert_allclose(vectors['projects_vector'], expected, atol=1e-6)
    assert set(vectors) == {'projects_vector', 'overall_vector'}
    assert vectorizer.build_section_texts({'skills': [], 'education': []}) == {}


def test_configured_esco_inference_failure_recovers(monkeypatch):
    from normalization.skill_normalizer import SkillNormalizer
    extractor = esco_skills.EscoSkillExtractor(
        skills=[{'label': 'Special skill', 'uri': 'urn:skill'}], cache_dir=None,
        embed_fn=Mock(side_effect=RuntimeError('model failed')))
    normalizer = SkillNormalizer(extractor=extractor)
    normalize_module = import_module('normalization.normalize_resume')
    monkeypatch.setattr(normalize_module, 'make_normalizer', lambda esco_csv, esco_cache_dir: normalizer)
    pending = queue.Queue()
    original = event(Resume('text', skills=Skills(other=['unknown phrase'])))
    handler.handle_normalization(original, resume_queue=pending)
    assert pending.empty()
    assert 'normalized_resume' not in original['data']
    extractor._embed_fn = lambda texts: np.ones((len(texts), 1), dtype=np.float32)
    handler.handle_normalization(original, resume_queue=pending)
    assert pending.get_nowait()['data']['normalized_resume']['skills'] == ['Special skill']


def test_esco_default_never_writes_source_directory(monkeypatch):
    monkeypatch.setattr(Path, 'mkdir', Mock(side_effect=PermissionError('read-only source')))
    extractor = esco_skills.EscoSkillExtractor(
        skills=[{'label': 'Special skill', 'uri': 'urn:skill'}],
        embed_fn=lambda texts: np.ones((len(texts), 1), dtype=np.float32))
    assert extractor.extract(['synthetic'])[0][0].label == 'Special skill'
    Path.mkdir.assert_not_called()


def test_result_queue_public_interface_is_bounded_and_retained(monkeypatch):
    import completion_results
    monkeypatch.setattr(completion_results, '_result_queue', None)
    results = completion_results.get_result_queue(2)
    results.put_nowait('completed')
    assert completion_results.get_result_queue() is results
    assert results.maxsize == 2
    assert results.get_nowait() == 'completed'
    results.task_done()


def test_esco_external_cache_directory(tmp_path):
    skills = [{'label': 'Special skill', 'uri': 'urn:skill'}]
    embed = Mock(side_effect=lambda texts: np.ones((len(texts), 1), dtype=np.float32))
    extractor = esco_skills.EscoSkillExtractor(skills=skills, embed_fn=embed, cache_dir=tmp_path)
    assert extractor.extract(['synthetic'])[0][0].label == 'Special skill'
    assert len(list(tmp_path.glob('*.npy'))) == 1
    embed.reset_mock()
    reloaded = esco_skills.EscoSkillExtractor(skills=skills, embed_fn=embed, cache_dir=tmp_path)
    assert reloaded.extract(['synthetic'])[0][0].label == 'Special skill'
    embed.assert_called_once_with(['synthetic'])


def test_resource_initialization_is_lazy_cached_and_clearable(monkeypatch):
    import runpy
    module = import_module('normalization.normalize_resume')
    factory = Mock(side_effect=lambda esco_csv, esco_cache_dir: Mock(extractor=None))
    monkeypatch.setattr(module, 'make_normalizer', factory)
    # Import/module evaluation alone must not construct expensive resources.
    namespace = runpy.run_path(model_resources.__file__)
    factory.assert_not_called()
    getter = namespace['get_normalizer']
    first = getter()
    assert getter() is first
    factory.assert_called_once_with(None, None)
    assert getter.cache_info().maxsize == 1
    getter.cache_clear()
    assert getter() is not first
    assert factory.call_count == 2
