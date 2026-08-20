/**
 * FaceID navbar widget: a button + dropdown modal that activates the webcam,
 * captures frames, sends them to POST /face/identify, and displays the
 * recognised person's name in real-time.
 *
 * Depends on: auth.js (Auth.authFetch, Auth.requireAuth).
 * Usage: include after auth.js, add <div id="faceid-slot"></div> in the navbar.
 */
(function () {
	'use strict';

	var slot = document.getElementById('faceid-slot');
	if (!slot) return;

	// -- Styles -----------------------------------------------------------------
	var style = document.createElement('style');
	style.textContent =
		'#faceid-btn{position:relative;display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid #2a313c;background:#161822;color:#94a3b8;transition:all .2s}' +
		'#faceid-btn:hover{border-color:#6c5ce7;color:#e2e8f0}' +
		'#faceid-btn.active{border-color:#22c55e;color:#22c55e;background:#22c55e10}' +
		'#faceid-panel{display:none;position:absolute;top:calc(100% + 6px);right:0;width:280px;background:#161822;border:1px solid #2a313c;border-radius:12px;padding:12px;z-index:100;box-shadow:0 8px 32px rgba(0,0,0,.5)}' +
		'#faceid-panel.open{display:flex;flex-direction:column;gap:10px}' +
		'#faceid-video{width:100%;height:180px;background:#0f1216;border-radius:8px;object-fit:cover;display:block}' +
		'#faceid-result{min-height:36px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}' +
		'#faceid-result .name{font-size:14px;font-weight:700;color:#22c55e}' +
		'#faceid-result .sim{font-size:11px;color:#64748b;margin-top:2px}' +
		'#faceid-result .idle{font-size:11px;color:#475569}' +
		'#faceid-result .no-face{font-size:11px;color:#f59e0b}' +
		'#faceid-controls{display:flex;gap:6px}' +
		'#faceid-controls button{flex:1;padding:5px 0;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;border:none;transition:all .15s}' +
		'.faceid-start{background:#6c5ce7;color:#fff}.faceid-start:hover{background:#5b4bc4}' +
		'.faceid-stop{background:#ef4444;color:#fff}.faceid-stop:hover{background:#dc2626}';
	document.head.appendChild(style);

	// -- HTML -------------------------------------------------------------------
	slot.innerHTML =
		'<div style="position:relative">' +
		'<button id="faceid-btn" type="button" title="Face ID – identify a person via webcam">' +
		'<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10S2 17.523 2 12z"/></svg>' +
		'Face ID' +
		'</button>' +
		'<div id="faceid-panel">' +
		'<video id="faceid-video" autoplay playsinline muted></video>' +
		'<div id="faceid-result"><span class="idle">Press Start to begin</span></div>' +
		'<div id="faceid-controls">' +
		'<button class="faceid-start" id="faceid-start">Start</button>' +
		'<button class="faceid-stop" id="faceid-stop" style="display:none">Stop</button>' +
		'</div>' +
		'</div>' +
		'</div>';

	// -- Elements ----------------------------------------------------------------
	var btn = document.getElementById('faceid-btn');
	var panel = document.getElementById('faceid-panel');
	var video = document.getElementById('faceid-video');
	var resultEl = document.getElementById('faceid-result');
	var startBtn = document.getElementById('faceid-start');
	var stopBtn = document.getElementById('faceid-stop');

	var stream = null;
	var timer = null;
	var running = false;

	// -- Panel toggle ------------------------------------------------------------
	btn.addEventListener('click', function (e) {
		e.stopPropagation();
		if (panel.classList.contains('open')) {
			closePanel();
		} else {
			panel.classList.add('open');
			btn.classList.add('active');
		}
	});

	document.addEventListener('click', function (e) {
		if (!panel.contains(e.target) && e.target !== btn) closePanel();
	});

	function closePanel() {
		panel.classList.remove('open');
		btn.classList.remove('active');
	}

	// -- Camera ------------------------------------------------------------------
	startBtn.addEventListener('click', function () {
		resultEl.innerHTML = '<span class="idle">Starting camera…</span>';
		navigator.mediaDevices
			.getUserMedia({ video: { facingMode: 'user', width: { ideal: 320 }, height: { ideal: 240 } } })
			.then(function (s) {
				stream = s;
				video.srcObject = stream;
				startBtn.style.display = 'none';
				stopBtn.style.display = '';
				running = true;
				resultEl.innerHTML = '<span class="idle">Scanning…</span>';
				scheduleFrame();
			})
			.catch(function (err) {
				resultEl.innerHTML = '<span class="no-face">Camera access denied</span>';
				console.error('[faceid] getUserMedia error:', err);
			});
	});

	stopBtn.addEventListener('click', stopCamera);

	function stopCamera() {
		running = false;
		if (timer) { clearTimeout(timer); timer = null; }
		if (stream) {
			stream.getTracks().forEach(function (t) { t.stop(); });
			stream = null;
		}
		video.srcObject = null;
		startBtn.style.display = '';
		stopBtn.style.display = 'none';
		resultEl.innerHTML = '<span class="idle">Press Start to begin</span>';
	}

	// -- Frame capture + identify ------------------------------------------------
	function scheduleFrame() {
		if (!running) return;
		timer = setTimeout(function () {
			if (!running) return;
			captureAndIdentify();
			scheduleFrame();
		}, 800); // ~1.2 fps to avoid overloading the server
	}

	function captureAndIdentify() {
		if (!stream || !running) return;

		var c = document.createElement('canvas');
		c.width = video.videoWidth || 320;
		c.height = video.videoHeight || 240;
		c.getContext('2d').drawImage(video, 0, 0, c.width, c.height);

		var dataUrl = c.toDataURL('image/jpeg', 0.6);
		var b64 = dataUrl.split(',')[1];
		if (!b64) return;

		resultEl.innerHTML = '<span class="idle">Identifying…</span>';

		Auth.authFetch('/face/identify', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ frame: b64 }),
		})
			.then(function (r) {
				if (!r.ok) throw new Error('identify failed');
				return r.json();
			})
			.then(function (data) {
				if (!running) return;
				if (data.matched) {
					var pct = data.similarity != null ? (data.similarity * 100).toFixed(1) + '%' : '';
					resultEl.innerHTML =
						'<div class="name">' + escapeHtml(data.name) + '</div>' +
						'<div class="sim">' + pct + ' match</div>';
				} else {
					resultEl.innerHTML = '<span class="no-face">No match found</span>';
				}
			})
			.catch(function () {
				if (running) resultEl.innerHTML = '<span class="no-face">识别错误</span>';
			});
	}

	function escapeHtml(s) {
		var d = document.createElement('div');
		d.appendChild(document.createTextNode(s));
		return d.innerHTML;
	}

	// Cleanup on page unload
	window.addEventListener('beforeunload', stopCamera);
})();
