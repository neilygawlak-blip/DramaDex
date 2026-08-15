@echo off
rem One-command ship: pull text edits, run the fix pipeline, rebuild, deploy.
rem First time only: run  npx wrangler login  (browser opens, click Allow).
git -C private pull
pushd private && python apply_fixes_v2.py || (popd & exit /b 1)
popd
rem No args = every play in the PLAYS registry.
python build_character_pages.py || exit /b 1
python build_french_scenes.py private/see_how_they_run_fixed.txt private/cast_see_how_they_run.txt private/french_scenes.html || exit /b 1
python prep_deploy.py private/handouts private/deploy || exit /b 1
rem wrangler.toml names the project, the output folder and the Voice
rem Booth's KV binding; plain deploy reads all of it from there.
rem Pinned: 4.121.0 shipped broken on npm (miniflare version not
rem published, Aug 11 2026). Bump the pin when convenient.
npx wrangler@4.120.1 pages deploy
