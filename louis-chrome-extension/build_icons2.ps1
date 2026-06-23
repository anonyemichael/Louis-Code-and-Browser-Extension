$svg16 = @"
<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 2 v10 a2 2 0 0 0 2 2 h4" stroke="#da7756" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

$svg48 = @"
<svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="3" y="4" width="42" height="42" rx="10" fill="#000000" fill-opacity="0.15"/>
  <rect x="3" y="3" width="42" height="42" rx="10" fill="#ffffff" stroke="#e4e4e7" stroke-width="1"/>
  <path d="M18 12 v21 a3 3 0 0 0 3 3 h9" stroke="#da7756" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

$svg128 = @"
<svg width="128" height="128" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="12" width="112" height="112" rx="28" fill="#000000" fill-opacity="0.1"/>
  <rect x="8" y="8" width="112" height="112" rx="28" fill="#ffffff" stroke="#e4e4e7" stroke-width="2"/>
  <path d="M48 32 v56 a8 8 0 0 0 8 8 h24" stroke="#da7756" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

Set-Content -Path "icons/icon-16.svg" -Value $svg16 -Encoding UTF8
Set-Content -Path "icons/icon-48.svg" -Value $svg48 -Encoding UTF8
Set-Content -Path "icons/icon-128.svg" -Value $svg128 -Encoding UTF8

magick -background none icons/icon-16.svg icons/icon-16.png
magick -background none icons/icon-48.svg icons/icon-48.png
magick -background none icons/icon-128.svg icons/icon-128.png
