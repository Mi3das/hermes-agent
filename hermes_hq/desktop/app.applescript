-- HERMES HQ AppleScript applet wrapper.
--
-- Why an applet? A plain shell-script .app bundle runs no Cocoa event loop, so
-- `tell application "HERMES HQ" to quit` (used by uninstallers, Script Editor,
-- logout helpers) is silently ignored. An osacompiled applet DOES run an event
-- loop and receives the `quit` Apple event, which lets us shut the server down
-- cleanly through /api/shutdown before the process group is reaped.
--
-- REPO_DIR and PORT are templated in at build time by build_app.sh.

property repoDir : "__REPO_DIR__"
property thePort : "__PORT__"
property theHost : "127.0.0.1"

on baseURL()
	return "http://" & theHost & ":" & thePort
end baseURL

on serverUp()
	try
		do shell script "/usr/bin/curl -s -o /dev/null --max-time 1 " & quoted form of (baseURL() & "/api/info")
		return true
	on error
		return false
	end try
end serverUp

on run
	-- If a server is already up on our port, just open the dashboard.
	if serverUp() then
		do shell script "/usr/bin/open " & quoted form of (baseURL())
		return
	end if
	-- Otherwise start it via the shell launcher (fire-and-forget; the launcher
	-- backgrounds the server in its own session and exits). The applet stays
	-- alive to own the `quit` event. Prefer the build-rendered launcher (with
	-- REPO_DIR/PORT baked in); fall back to the raw template if absent.
	set rendered to repoDir & "/hermes_hq/desktop/launcher.rendered.sh"
	set rawLauncher to repoDir & "/hermes_hq/desktop/launcher.sh"
	try
		do shell script "test -f " & quoted form of rendered
		set launcher to quoted form of rendered
	on error
		set launcher to quoted form of rawLauncher
	end try
	try
		do shell script "/bin/bash " & launcher & " > /dev/null 2>&1 &"
	end try
end run

-- Apple event handler: fired by `tell app to quit`, Cmd-Q, logout, shutdown.
on quit
	try
		-- Graceful: ask the server to flush state and exit itself.
		do shell script "/usr/bin/curl -s -o /dev/null --max-time 2 -X POST " & quoted form of (baseURL() & "/api/shutdown")
	end try
	-- Belt-and-suspenders: reap anything still bound to our port.
	try
		do shell script "/usr/bin/pkill -f " & quoted form of ("hermes_hq --host " & theHost & " --port " & thePort)
	end try
	continue quit
end quit

-- Stay-open applets call `idle` periodically. We do nothing heavy here; the
-- handler just keeps the app alive in the background so it can receive `quit`.
-- Return value = seconds until the next idle call.
on idle
	return 30
end idle

