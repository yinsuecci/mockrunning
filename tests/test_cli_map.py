from ios_location_controller import cli


def test_map_entry_runs_server_without_asyncio_runner(monkeypatch):
    calls = []

    def no_async_runner(_):
        raise AssertionError('The synchronous HTTP server must handle Ctrl+C directly')

    monkeypatch.setattr('sys.argv', ['ios-location', 'map', '--port', '18765'])
    monkeypatch.setattr('ios_location_controller.web.serve', lambda host, port: calls.append((host, port)))
    monkeypatch.setattr(cli.asyncio, 'run', no_async_runner)
    cli.main()
    assert calls == [('127.0.0.1', 18765)]
