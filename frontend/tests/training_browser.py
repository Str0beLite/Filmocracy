"""Browser checks with synthetic images and mocked provider/API boundaries.
Run against Vite; no Google credentials or live APIs are needed.
Requires Python playwright and Chrome (or Playwright's installed Chromium).
"""
import base64
import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ORIGIN = os.getenv('TRAINING_TEST_ORIGIN', 'http://127.0.0.1:5177')
CHROME = os.getenv('TRAINING_TEST_CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def check(browser, width, height, existing=None, shot_count=3):
    page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
    if existing == 'main':
        page.add_init_script("localStorage.setItem('tandem.device-user.phone', 'phone-' + '1'.repeat(32))")
    elif existing == 'trainer':
        page.add_init_script("sessionStorage.setItem('tandem.guest.token', 'guest-' + '2'.repeat(64))")
    errors, requests, votes = [], [], []
    state = {'next': 0, 'failed': False, 'uploaded': False, 'rejected': False}
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('https://www.youtube-nocookie.com/**', lambda route: route.fulfill(body='<html><body style="background:#0c0708;color:#b9a391;font:16px sans-serif;display:grid;place-items:center;height:90vh">Trailer test fixture</body></html>', content_type='text/html'))
    page.route('https://accounts.google.com/**', lambda route: route.abort())
    credentials = set()

    def api(route):
        req = route.request
        path = req.url.split('/api', 1)[1]
        requests.append(path)
        credential = req.headers.get('authorization', '')
        assert re.fullmatch(r'Bearer (guest-[a-f0-9]{64}|phone-[a-f0-9]{32})', credential), 'Expected an anonymous browser credential'
        if existing == 'main':
            assert credential == 'Bearer phone-' + '1' * 32
        elif existing == 'trainer':
            assert credential == 'Bearer guest-' + '2' * 64
        credentials.add(credential)
        body = {}
        status = 200
        if path == '/ready':
            body = {'training_enabled': True}
        elif path == '/profiles/me':
            assert req.post_data_json == {'display_name': 'Test Viewer'}
        elif path == '/training/feeds':
            assert req.post_data_buffer.count(b'name="files"') == shot_count
            state['uploaded'] = True
            body = {'feed_id': 'fixture-feed', 'tags': {'comedy': 1, 'warm': 0.8}}
        elif path == '/training/feeds/fixture-feed/next':
            assert state['uploaded']
            assert 'comedy' in req.post_data_json['boost']
            state['next'] += 1
            if state['next'] == 2:
                status, body = 503, {'detail': 'Trailer checks unavailable; try again'}
                state['failed'] = True
            else:
                idx = state['next']
                body = {'rec_id': idx, 'score': 0.731234, 'w_version': 0, 'movie': {'id': idx, 'title': f'Test Movie {idx}', 'year': 2001, 'trailer_key': 'abcdefghijk', 'overview': 'A synthetic movie for browser verification.'}}
        elif path == '/feedback':
            assert req.post_data_json['label'] in ('love', 'nah', 'seen_loved', 'seen_disliked')
            if req.post_data_json['label'] == 'seen_disliked' and not state['rejected']:
                state['rejected'] = True
                status, body = 422, {'detail': [{'loc': ['body', 'label'], 'msg': 'Backend does not support this vote label'}]}
            else:
                votes.append(req.post_data_json)
        else:
            raise AssertionError(f'Training unexpectedly called {path}')
        route.fulfill(status=status, json=body)

    page.route(f'{ORIGIN}/api/**', api)
    page.goto(f'{ORIGIN}/training')
    page.wait_for_load_state('networkidle')
    assert page.get_by_text('Sign in with Google', exact=False).count() == 0
    page.screenshot(path=f'/private/tmp/tandem-training-name-{width}.png', full_page=True)
    def appearance(selector):
        return page.locator(selector).evaluate("el => { const s = getComputedStyle(el); return { font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, color: s.color, background: s.backgroundColor, radius: s.borderRadius }; }")
    training_style = {selector: appearance(selector) for selector in ['.wordmark', '.ps-title', '.field-text']}
    assert page.get_by_label('First name').get_attribute('maxlength') == '20'
    page.get_by_label('First name').fill('Test Viewer')
    page.get_by_role('button', name='Continue', exact=True).click()
    page.get_by_role('button', name='Laugh until it hurts').click()
    assert page.get_by_role('button', name='Laugh until it hurts').get_attribute('aria-pressed') == 'true'
    page.screenshot(path=f'/private/tmp/tandem-training-feeling-{width}.png', full_page=True)
    page.get_by_role('button', name='Continue', exact=True).click()
    upload = page.get_by_label('Choose Explore screenshots')
    assert page.get_by_role('button', name='Read My Feed', exact=True).is_disabled()
    upload.set_input_files([{'name': 'one.png', 'mimeType': 'image/png', 'buffer': PNG}])
    assert page.get_by_role('button', name='Read My Feed', exact=True).is_enabled()
    if shot_count > 1:
        upload.set_input_files([{'name': f'{i}.png', 'mimeType': 'image/png', 'buffer': PNG} for i in range(2, shot_count + 1)])
    page.get_by_role('button', name='Remove screenshot 1').click()
    if shot_count == 1:
        assert page.get_by_role('button', name='Read My Feed', exact=True).is_disabled()
    else:
        assert page.get_by_role('button', name='Read My Feed', exact=True).is_enabled()
    upload.set_input_files([{'name': 'replacement.png', 'mimeType': 'image/png', 'buffer': PNG}])
    page.screenshot(path=f'/private/tmp/tandem-training-shots-{width}.png', full_page=True)
    page.get_by_role('button', name='Read My Feed', exact=True).click()
    page.get_by_role('heading', name='Test Movie 1', exact=True).wait_for()
    page.wait_for_function("() => {const buttons = [...document.querySelectorAll('.training-votes .vote-btn')]; return buttons.length === 2 && buttons.every(b => {const s = getComputedStyle(b).scale; return s === 'none' || Math.abs(parseFloat(s) - 1) < 0.001;});}")
    page.evaluate('window.scrollTo(0, 0)')
    assert page.get_by_text('AI match score: 0.731.', exact=False).is_visible()
    player = page.locator('iframe').bounding_box()
    assert player
    assert page.locator('.training-votes button').count() == 2
    assert page.get_by_role('button', name=re.compile(r'^(Liked it|Interested)$')).count() == 0
    for name in ['Watched', 'Not watched']:
        box = page.get_by_role('button', name=name, exact=True).bounding_box()
        assert box and box['y'] >= player['y'] + player['height']
        assert box['y'] + box['height'] <= height
    page.screenshot(path=f'/private/tmp/filmocracy-training-seen-{width}.png', full_page=True)
    page.get_by_role('button', name='Watched', exact=True).click()
    assert not votes, 'Seen choice must not submit feedback'
    page.get_by_role('button', name='Change', exact=True).click()
    page.get_by_role('button', name='Watched' if existing else 'Not watched', exact=True).click()
    assert page.locator('.training-votes button').count() == 2
    assert page.get_by_role('button', name='Watched', exact=True).count() == 0
    page.get_by_role('button', name='Liked it' if existing else 'Interested', exact=True).wait_for()
    page.screenshot(path=f'/private/tmp/filmocracy-training-vote-{width}.png', full_page=True)
    page.get_by_role('button', name='Liked it' if existing else 'Interested', exact=True).click()
    page.get_by_text('1 vote saved', exact=False).wait_for()
    assert len(votes) == 1 and votes[0]['label'] == ('seen_loved' if existing else 'love')
    page.get_by_role('button', name='Next Trailer', exact=True).click()
    page.get_by_role('alert').filter(has_text='Trailer checks unavailable').wait_for()
    assert len(votes) == 1
    page.get_by_role('button', name='Next Trailer', exact=True).click()
    page.get_by_role('heading', name='Test Movie 3', exact=True).wait_for()
    assert page.locator('iframe').get_attribute('src').startswith('https://www.youtube-nocookie.com/')
    assert page.get_by_role('button', name=re.compile(r'^(Liked it|Interested)$')).count() == 0
    page.get_by_role('button', name='Watched' if existing else 'Not watched', exact=True).click()
    assert len(votes) == 1
    page.get_by_role('button', name='Disliked it' if existing else 'Not interested', exact=True).click()
    if existing:
        page.get_by_role('alert').filter(has_text='label: Backend does not support this vote label').wait_for()
        assert len(votes) == 1, 'Rejected vote must stay pending'
        page.get_by_role('button', name='Disliked it' if existing else 'Not interested', exact=True).click()
    page.get_by_text('2 votes saved', exact=False).wait_for()
    assert len(votes) == 2 and votes[1]['label'] == ('seen_disliked' if existing else 'nah')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    path = Path('/private/tmp') / f'tandem-training-{width}.png'
    page.screenshot(path=str(path), full_page=True)
    page.get_by_role('button', name='Finish for now').click()
    page.get_by_role('heading', name='That’s a wrap. Thank you.').wait_for()
    page.reload()
    page.get_by_label('First name').wait_for()
    page.wait_for_load_state('networkidle')
    assert len(credentials) == 1, 'Guest identity must survive refresh'
    assert not errors, errors
    assert not any('/sessions' in path for path in requests)
    page.goto(f'{ORIGIN}/phone/sign-in')
    page.get_by_role('heading', name='What do your friends call you?').wait_for()
    page.wait_for_load_state('networkidle')
    for selector, expected in training_style.items():
        assert appearance(selector) == expected, f'Training must match the main phone style for {selector}'
    page.screenshot(path=f'/private/tmp/filmocracy-main-name-{width}.png', full_page=True)
    assert page.get_by_text('Sign in with Google', exact=False).count() == 0
    page.close()
    print(f'PASS {width}x{height} ({existing or "new"} identity): anonymous identity, {shot_count} screenshots, feedback, retry, no room, no overflow; {path}')


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=CHROME if Path(CHROME).exists() else None)
    try:
        check(browser, 390, 844)
        check(browser, 1280, 900)
        check(browser, 390, 844, existing="main", shot_count=1)
        check(browser, 390, 844, existing="trainer", shot_count=2)
    finally:
        browser.close()
