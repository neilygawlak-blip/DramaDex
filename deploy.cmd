@echo off
rem One-command ship: pull text edits, rebuild pages, push to Cloudflare.
rem First time only: run  npx wrangler login  (browser opens, click Allow).
git -C private pull
python build_character_pages.py private/see_how_they_run_raw.txt private/cast_see_how_they_run.txt private/handouts || exit /b 1
python build_french_scenes.py private/see_how_they_run_raw.txt private/cast_see_how_they_run.txt private/french_scenes.html || exit /b 1
python prep_deploy.py private/handouts private/deploy || exit /b 1
npx wrangler pages deploy private/deploy --project-name=dramadex
