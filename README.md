# webquery – óránkénti árfigyelő

Konzolos Python program, amely óránként lekéri a `config.yaml`-ban megadott termékek
árát (Amazonnál a fő ajánlatot, azaz a Buy Box árát és az elérhetőséget), elmenti
SQLite-ba, és e-mailt küld, ha az ár a megadott limit alá megy.

## Telepítés

Egyszeri, sudo-t igénylő lépések (a saját, sudo joggal rendelkező fiókodból):

```sh
sudo apt install python3-venv          # a venv létrehozásához kell
sudo loginctl enable-linger claude     # hogy a user timer bejelentkezés nélkül is fusson
```

Utána a `claude` felhasználóként:

```sh
cd ~/webquery
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env && chmod 600 .env   # töltsd ki az SMTP-adatokat
.venv/bin/python -m webquery test-mail   # próba e-mail
.venv/bin/python -m webquery check --dry-run
```

## systemd user timer

```sh
mkdir -p ~/.config/systemd/user
ln -sf ~/webquery/systemd/webquery.service ~/webquery/systemd/webquery.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now webquery.timer
systemctl --user list-timers webquery.timer
journalctl --user -u webquery.service -n 20   # napló
```

## Használat

```sh
.venv/bin/python -m webquery check            # egy futás (e-mail, ha a limit alatt)
.venv/bin/python -m webquery check --dry-run  # e-mail nélkül
.venv/bin/python -m webquery history -n 50    # utolsó mérések
.venv/bin/python -m unittest                  # tesztek
```

## Működés

- Az ár euróban jön: a program az `i18n-prefs=EUR` sütit küldi, mert az Amazon
  egyébként a látogató országa szerint (pl. HUF) írná ki. Más pénznem esetén a mérés hibának számít.
- E-mail csak akkor megy, ha a termék elérhető és az ár a limit alatt van, és vagy most
  ment a limit alá, vagy tovább csökkent az utolsó értesítés óta (nincs óránkénti ismétlés).
- CAPTCHA vagy tiltás esetén a program nem próbálja megkerülni: `blocked` státusszal
  rögzíti, és hibakóddal lép ki. Ha az oldal szerkezete változik, a HTML a `debug/` mappába kerül.
- Titkok csak a `.env` fájlban vannak, ami a `.gitignore`-ban szerepel.
