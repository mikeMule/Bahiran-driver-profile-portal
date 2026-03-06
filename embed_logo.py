import base64

with open('image/logo.png', 'rb') as f:
    b64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')

with open('register.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

changed = False
for i, line in enumerate(lines):
    # Fix header logo-box — replace any logo-box that doesn't have an img yet
    if 'class="logo-box"' in line and '<img' not in line:
        lines[i] = '  <div class="logo-box"><img src="' + b64 + '" alt="MotoReg Ethiopia" style="width:100%;height:100%;object-fit:contain;"></div>\n'
        print(f'Patched logo-box on line {i+1}')
        changed = True
    # Fix favicon link in head
    if line.strip().startswith('<title>') and not any('rel="icon"' in l for l in lines[:i+5]):
        lines[i] = lines[i].replace(
            '</title>',
            '</title>\n<link rel="icon" href="' + b64 + '" type="image/png">'
        )
        print(f'Added favicon after line {i+1}')
        changed = True

if changed:
    with open('register.html', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Done!')
else:
    print('Nothing to patch — logo-box or favicon may already be set.')
