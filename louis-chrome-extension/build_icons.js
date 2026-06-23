const sharp = require('sharp');
const fs = require('fs');

const svg16 = `
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
`;

const svg48 = `
<svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
`;

const svg128 = `
<svg width="128" height="128" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="24" height="24" rx="5" fill="#fdfdfd"/>
  <path d="M8 4v14a2 2 0 002 2h6" stroke="#da7756" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
`;

async function build() {
  if (!fs.existsSync('./icons')) {
    fs.mkdirSync('./icons');
  }
  await sharp(Buffer.from(svg16)).png().toFile('./icons/icon-16.png');
  await sharp(Buffer.from(svg48)).png().toFile('./icons/icon-48.png');
  await sharp(Buffer.from(svg128)).png().toFile('./icons/icon-128.png');
  console.log("Icons generated successfully!");
}

build().catch(console.error);
