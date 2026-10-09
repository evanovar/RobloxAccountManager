@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
pushd "%~dp0.." || exit /b 1
uv.exe run --locked --isolated --managed-python --group build python -I scripts/build.py
set "ram_build_exit=%ERRORLEVEL%"
popd
exit /b %ram_build_exit%
