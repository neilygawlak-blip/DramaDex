@echo off
rem One-command ship: pull text edits, run the fix pipeline, rebuild, deploy.
rem First time only: run  npx wrangler login  (browser opens, click Allow).
git -C private pull
pushd private && python apply_fixes_v2.py || (popd & exit /b 1)
popd
python build_character_pages.py private/see_how_they_run_fixed.txt private/cast_see_how_they_run.txt private/handouts || exit /b 1
python build_french_scenes.py private/see_how_they_run_fixed.txt private/cast_see_how_they_run.txt private/french_scenes.html || exit /b 1
python prep_deploy.py private/handouts private/deploy || exit /b 1
rem wrangler.toml names the project, the output folder and the Voice
rem Booth's R2 bucket binding; plain deploy reads all of it from there.
npx wrangler pages deploy
