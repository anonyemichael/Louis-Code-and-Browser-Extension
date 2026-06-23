$svg16 = @"
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

$svg48 = @"
<svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

$svg128 = @"
<svg width="128" height="128" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@

Set-Content -Path "icons/icon-16.svg" -Value $svg16 -Encoding UTF8
Set-Content -Path "icons/icon-48.svg" -Value $svg48 -Encoding UTF8
Set-Content -Path "icons/icon-128.svg" -Value $svg128 -Encoding UTF8

magick -background none icons/icon-16.svg icons/icon-16.png
magick -background none icons/icon-48.svg icons/icon-48.png
magick -background none icons/icon-128.svg icons/icon-128.png
