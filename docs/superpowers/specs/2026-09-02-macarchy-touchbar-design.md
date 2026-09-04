# macarchy-touchbar — une Touch Bar à nous, extensible par modules

Date : 2026-09-02
Statut : validé, en attente du plan d'implémentation

## Pourquoi

`macarchy-touchbar` rend la Touch Bar du MacBook Pro M2 contextuelle en réécrivant
le `config.toml` de tiny-dfr à chaque changement de fenêtre. Ça marche, et ça
plafonne : tiny-dfr ne sait dessiner que quatre choses (icône SVG, texte,
heure, batterie), en un seul blanc, réagissant à un tap, et il tient seul le
périphérique.

Les griefs, dans l'ordre où ils se voient :

1. **Pas iconique.** Des SVG dessinés à la main à graisses inégales, tous
   blancs, sans accent de couleur nulle part.
2. **Pas de slider.** Régler la luminosité, c'est taper trois fois sur « + ».
3. **Un groupe se ferme dès qu'on s'en sert** (`collapse_on_action`), donc
   trois tapes = trois réouvertures.
4. **Jarvis n'a qu'un glyphe.** Soixante pixels de haut suffisent à un poisson
   animé, un vumètre et une réponse qui se tape.
5. **Rien n'est extensible.** Chaque idée est un `type = "…"` de plus dans un
   script de 900 lignes.

Constat mesuré le 2026-09-02 (spike jetable, `spike_drm.py`) : le bar est un
vrai écran DRM (`/dev/dri/card3`, driver `adp`, connecteur DSI-1, mode
**60×2008**) et un écran tactile evdev (`/dev/input/event3`, « Mac14,7 Touch
Bar »). Depuis Python, `libdrm` par ctypes pose un dumb buffer XRGB8888 et
`SetCrtc` l'affiche en 13 ms ; `DirtyFB` pousse une image suivante en 2,5 ms ;
le tactile brut livre des glissés continus (X 1100–19900, Y jusqu'à ~570).
Contrainte apprise : le dumb buffer doit faire **64** pixels de large (pitch
256), sinon l'image est hachurée.

## Ce qu'on construit

**macarchy-touchbar** remplace tiny-dfr et macarchy-touchbar. C'est un daemon Python en
session utilisateur qui tient l'écran et le tactile, un toolkit de widgets au
look macOS, et un **contrat de module** identique dans l'esprit à celui du
Control Center : les fonctionnalités sont des modules découverts par le
registre de plugins Omarchy sous un kind dédié, et les modules internes
utilisent exactement le même contrat que les externes.

Décisions prises pendant le brainstorming :

| Question | Décision |
|---|---|
| Qui tient les pixels | Notre daemon (pas de fork Rust, pas de sortie Hyprland) |
| Direction visuelle | macOS Touch Bar fidèle : noir, pilules grises, glyphes blancs, accents couleur là où macOS en met |
| Jarvis | Prise de barre à chaud pendant un échange ; bouton-poisson au repos |
| Sliders | Geste macOS complet : sliders dans les groupes, glisser depuis le bouton replié |
| Groupes | Restent ouverts jusqu'au ✕, un changement de fenêtre ou l'inactivité |
| Icônes | Material Symbols Rounded (police variable, vendue dans le dépôt), Papirus pour les apps, Inter pour le texte |
| Composants retenus | Now Playing avec pochette, HUD volume/luminosité, vignette de capture, Scrubber, Claude Code sur la barre, spectre audio, vie au repos |
| Écarté | Notification riche avec actions (la notification reste texte + ✕) |

## Emplacement et process

- Dépôt `~/Work/macarchy-touchbar`, miroir `github.com/macarchy/macarchy-touchbar`, avec
  son `install.sh` (même modèle que jarvis).
- Binaire `~/.local/bin/macarchy-touchbar` (symlink vers `bin/macarchy-touchbar` du
  dépôt : pas de copie qui dérive).
- Unité **systemd user** `macarchy-touchbar.service` (`Restart=on-failure`,
  journal), démarrée depuis `~/.config/hypr/autostart.lua`. La leçon du wake
  daemon de Jarvis : un daemon qui meurt sans journal n'est pas diagnostiquable.
- Accès matériel sans root : l'utilisateur entre dans le groupe `video`
  (card3 est `root:video 0660`, et la règle udev de tiny-dfr le sort de seat0,
  donc aucune ACL logind) ; une règle udev rend `/dev/uinput` accessible au
  groupe `input`. tiny-dfr est désactivé **et masqué**.
- Rétroéclairage du bar (`/sys/class/backlight/228600000.dsi.0`) écrit via
  logind `SetBrightness` sur D-Bus, le chemin d'macarchy-als.

## Le moteur

### Affichage

- Ouvre card3, prend le connecteur connecté et son premier mode (60×2008),
  alloue un dumb buffer **64×2008** XRGB8888, `AddFB`, mmap.
- Le mmap est enveloppé dans une `cairo.ImageSurface` (create_for_data, stride
  = pitch). Les widgets dessinent dans une **scène paysage 2008×60** ; une
  rotation cairo unique la pose dans le buffer portrait ; `DirtyFB` sur le
  rectangle modifié.
- Aucune horloge de rendu : on redessine sur invalidation, coalescée, plafond
  30 images/s. Seuls les rectangles invalidés sont repeints, un seul DirtyFB
  par image.
- Luminosité du bar asservie à l'écran principal (`apple-panel-bl`, inotify),
  atténuée après 60 s sans toucher, éteinte après 5 min. Le premier toucher
  sur une barre éteinte ne fait que la réveiller (macOS). Les scènes réveillent
  la barre.
- À SIGTERM : barre peinte en noir, master DRM relâché, uinput fermé.

### Tactile

- Lecture brute de event3 (pas de libinput), protocole multitouch B (slots,
  `ABS_MT_TRACKING_ID`, `ABS_MT_POSITION_X/Y`, `BTN_TOUCH`). Plages d'axes
  lues par `EVIOCGABS` et projetées en pixels de la scène paysage.
- Reconnaisseur de gestes, un seul doigt actif (le second est ignoré) :
  - `press` (immédiat, pour l'enfoncement visuel),
  - `tap` : relâché < 300 ms et déplacement < 12 px,
  - `long-press` : 500 ms sans déplacement > 12 px,
  - `drag` : déplacement > 12 px, **capturé par le widget touché au départ**,
    avec `drag-end` au relâché,
  - `release` dans tous les cas.
- Les widgets agissent au relâché (`tap`), sauf Slider et Scrubber qui
  suivent le doigt. Un glissé qui sort du widget ne le déclenche pas.

### Clavier virtuel et Fn

- Un uinput déclarant d'emblée **tout** KEY_0..KEY_MAX : le gel des
  capacités de tiny-dfr disparaît, et avec lui F13–F24 et le pont dans
  `bindings.lua`.
- La couche Fn (F1–F12 quand Fn est enfoncé) vient de l'écoute de `KEY_FN` sur
  le clavier interne (evdev, seat0). Elle prend toute la barre le temps de
  l'appui.

### Boucle et robustesse

- Une boucle `selectors` unique : DRM (vblank inutile, on n'attend pas),
  event3, clavier interne, socket IPC, inotify sur layouts.toml, sur les
  modules et sur le backlight, minuteurs, fd des modules.
- Chaque appel d'un module est enveloppé : une exception marque le module
  **en panne**, ses widgets dessinent `⚠`, le journal dit pourquoi, une
  sauvegarde du fichier le recharge. Le moteur ne partage aucune exception avec
  les modules.
- Un module ne bloque jamais par construction : `api.run` est asynchrone et
  rien dans `api` n'attend.

## Le toolkit

### Grille et palette (macOS fidèle)

- Fond `#000`. Pilule 60 px (toute la hauteur), rayon 6, marge extérieure 8 px,
  espacement 6, boutons 130 px. Remplissage `#333`, enfoncée `#666`,
  active = accent.
- Glyphe 36 px blanc centré. Texte Inter Medium 22 px, blanc.
- Ces tailles (60 / 36 / 130) remplacent les 44 / 24 d'origine : calibré sur le
  matériel le 2026-09-02 — à 44 px la pilule laisse deux bandes noires que
  l'écran, très allongé, rend beaucoup plus visibles qu'en maquette.
- Accents : slider blanc sur rail `#555` ; batterie verte en charge, rouge
  sous 20 % ; mode nuit orange ; Ne pas déranger violet ; Jarvis prend les
  couleurs de sa palette de sprites ; permission Claude Code ambre.
- Enfoncement dessiné dès `press`, action à `tap`.

### Icônes

- **Material Symbols Rounded**, police variable (`fonts/` du dépôt, Apache
  2.0), rendue par Pango : `api.icon("brightness_high", size=24, tint=None,
  fill=0.0, weight=500)`. L'axe **FILL** anime contour → plein quand un bouton
  devient actif (200 ms).
- **Papirus** pour les icônes d'applications en couleur (fenêtre au focus,
  workspaces, notifications), résolues par `class` via l'index d'icônes XDG.
- Cache par (nom, taille, teinte, fill) en surfaces cairo.

### Widgets

Contrat commun, une classe chacun :

```python
class Widget:
    stretch = 1                      # poids dans la distribution de largeur
    def measure(self, ctx) -> int    # largeur préférée en px (0 = élastique)
    def draw(self, cr, rect, state)  # state: pressed/active/disabled
    def on_press(self, x)            # optionnels
    def on_tap(self, x)
    def on_long_press(self, x)
    def on_drag(self, x, dx)         # seulement s'il capture
    def on_drag_end(self, x)
```

| Widget | Rôle | Particularités |
|---|---|---|
| **Button** | icône et/ou texte | `active` (accent + FILL), `badge` (point ou compteur), `run` / `keys` / `group` / `close` |
| **Slider** | rail, portion parcourue, poignée 24 px, glyphes min/max | tap = saut, drag = continu, valeur livrée au plus 20 fois/s ; `slide_into` depuis un Button replié |
| **Label** | texte Pango balisé | alignement, largeur fixe ou élastique, ellipse à droite, défilement optionnel |
| **Sprite** | planche PNG, échelle entière au plus proche voisin | animations nommées avec cadence ; les planches 72×56 de Jarvis à 40 px (bouton) ou 54 px (scène) |
| **Meter** | barre de niveau, vumètre à bandes, progression | nourri par `set_level(v)` ou `set_bands([...])` |
| **Image** | pochette, vignette, icône Papirus | coins arrondis, ajustement |
| **Spacer** | vide | fixe ou élastique |
| **Scrubber** | bande d'éléments défilant d'un coup de doigt avec inertie | `items`, `selected`, tap = choisir, drag = défiler ; rendu par un dessinateur d'élément fourni par le client |

### Conteneurs

- **Layout** : zone gauche + zone droite, chacune une liste de widgets.
  Distribution : les largeurs mesurées d'abord, le reste réparti par
  `stretch`. Une zone qui ne tient pas ellipse ses Labels puis retire ses
  Spacers ; jamais de chevauchement.
- **Group** (Control Strip) : un Button qui, au `tap`, remplace la zone
  **gauche** par `✕` + ses enfants. La zone droite reste ; le bouton du groupe
  ouvert passe en actif. Se ferme au ✕, au changement de fenêtre, ou après
  `timeout` d'inactivité (15 s par défaut, 0 = jamais). **Une action dedans ne
  le ferme pas.** `slide_into` : un `drag` qui commence sur le bouton replié
  ouvre le groupe et transfère le doigt au slider nommé, sans lever.
- **Scene** : la barre entière cédée à un module, avec `priority` et `timeout`.
  Une seule scène visible : la plus prioritaire ; les autres attendent en pile.
  Un tap hors de tout widget de la scène la ferme si `dismissable`.
- **Pile d'affichage**, du dessus vers le dessous : couche Fn > Scene > Group
  ouvert > Layout courant.

## Le contrat de module

### Découverte

Même registre que le Control Center :

```json
"kinds": ["service", "control-center-module", "touchbar-module"],
"entryPoints": { "touchbarModule": "touchbar.py" },
"touchbarModule": { "apiVersion": 1 }
```

- Les modules externes sont lus dans `~/.config/omarchy/plugins/<id>/`. Un
  plugin désactivé dans le registre Omarchy n'est pas chargé.
- Les modules internes vivent dans `modules/<nom>/touchbar.py` du dépôt, avec
  un `manifest.json` minimal, et passent par le même chemin de chargement.
- L'identifiant d'un module est l'`id` du manifeste ; les widgets qu'il
  enregistre s'appellent `<id>.<nom>` (`macarchy.jarvis.fish`,
  `display.brightness`).
- **Jamais d'écriture dans le dossier d'un plugin à l'exécution** (le shell
  surveille ces dossiers et se recharge entièrement).

### Forme

```python
class Module:
    def setup(self, api): ...     # enregistre widgets, scènes, minuteurs, verbes IPC
    def teardown(self): ...       # optionnel : libère fd, processus enfants
```

Le module est importé par chemin dans son propre espace de noms ; ses
dépendances sont la bibliothèque standard, `cairo`, `gi` (Pango, Rsvg) et rien
d'autre. Il ne voit pas le moteur : seulement `api`.

### `api`

| Appel | Effet |
|---|---|
| `api.widget(name, factory)` | Enregistre une fabrique `factory(params) -> Widget` ; layouts.toml l'instancie par `widget = "<id>.<name>"` |
| `api.scene(name, factory)` | Enregistre une scène (un Layout pleine barre construit par la fabrique) |
| `api.show_scene(name, priority=50, timeout=None, dismissable=True)` / `api.hide_scene(name)` | Prise et rendu de la barre |
| `api.every(seconds, fn)` / `api.after(seconds, fn)` | Minuteurs ; retournent un handle annulable |
| `api.watch_file(path, fn)` / `api.watch_fd(fd, fn)` | inotify et fd dans la boucle |
| `api.run(argv, on_done=None, on_line=None)` | Sous-processus asynchrone ; `on_line` pour les flux (cava, playerctl --follow) |
| `api.ipc(verb, fn)` | `macarchy-touchbar <id> <verb> [args…]` arrive dans `fn(*args)` ; réponse optionnelle renvoyée au client |
| `api.context` / `api.on_context(fn)` | Fenêtre au focus (classe, titre), workspaces, Fn enfoncé, barre allumée |
| `api.keys([...])` | Frappe sur le clavier virtuel |
| `api.icon(...)`, `api.text(...)`, `api.image(path)`, `api.app_icon(cls)`, `api.theme` | Primitives de dessin et palette |
| `api.invalidate(widget=None)` | Demande de redessin (le widget, ou tout ce que le module a posé) |
| `api.log(...)` | Journal, préfixé de l'id du module |
| `api.state_dir` | `~/.local/state/macarchy-touchbar/<id>/` pour ce que le module doit persister |

### IPC

Socket Unix `$XDG_RUNTIME_DIR/macarchy-touchbar/sock`, une requête = une ligne
(`<module> <verb> [args…]` ou un verbe du moteur), une réponse = une ligne.
Verbes du moteur : `status`, `reload`, `group <nom>|close`, `screenshot
<png>`, `touch x,y [x2,y2]`, `brightness <n>|auto`. Le client est le même
exécutable (`macarchy-touchbar <…>`).

## Composition : layouts.toml v2

Fichier `~/.config/macarchy-touchbar/layouts.toml`, surveillé, appliqué à la
sauvegarde. Trois tables et des réglages.

```toml
[settings]
dim_after = 60          # s sans toucher avant d'atténuer
off_after = 300         # s avant d'éteindre (0 = jamais)
group_timeout = 15      # s d'inactivité avant de replier un groupe
hud = true              # slider furtif quand les touches clavier agissent

[items.newtab]
widget = "core.button"
icon = "add"
keys = ["LeftCtrl", "T"]

[items.menu]
widget = "core.button"
icon = "apps"
run = "omarchy menu"

[groups.display]
icon = "brightness_6"
items = ["display.brightness", "display.keyboard", "display.nightlight", "display.auto"]
slide_into = "display.brightness"

[layouts.default]
left  = ["menu", "macarchy.jarvis.fish", "workspaces.scrubber"]
right = ["group:media", "group:display", "group:system", "core.clock", "system.battery"]

[layouts.browser]
match = "firefox|zen|chromium|chrome|brave"
left  = ["menu", "macarchy.jarvis.fish", "back", "forward", "reload", "newtab", "closetab"]
right = ["group:media", "group:system", "core.clock", "system.battery"]
```

- Une référence est un nom d'`items`, ou `<id>.<widget>` avec ses valeurs par
  défaut, ou `group:<nom>`.
- Le premier `layouts.*` dont `match` (regex sur classe ou titre) correspond
  gagne ; `default` en repli. Le nom de la table vaut regex si `match` manque.
- Une référence vers un module absent ou en panne dessine `⚠` à sa place, la
  barre reste utilisable.
- Le fichier livré par `install.sh` reproduit l'usage actuel : défaut,
  navigateur, terminal, agent, couche Fn.

## Modules internes

Tous dans `modules/`, tous par le contrat ci-dessus. Aucun ne parle à un
autre : quand deux en ont besoin d'un même fait (le niveau audio), c'est le
moteur qui l'offre ou chacun le lit.

| Module | Widgets / scènes | Sources |
|---|---|---|
| `core` | button, slider, label, spacer, clock, image, scrubber ; couche Fn | — |
| `media` | now_playing (pochette, titre défilant, ligne de temps glissable), play/prev/next, volume (slider), mute, mic, spectrum (Meter à bandes) | `playerctl --follow` (metadata, position, `mpris:artUrl`), `wpctl`, `pw-mon` pour le HUD volume, `cava` en sortie brute |
| `display` | brightness (slider), keyboard (slider), nightlight, auto (ALS) ; scène HUD | sysfs backlight (inotify) → scène HUD priorité 20, 1,5 s ; `omarchy-brightness-*`, `macarchy-als toggle`, `omarchy toggle nightlight` |
| `system` | battery (icône + %, vert/rouge, temps restant en `long-press`), lock, charge_limit, screenshot ; scène vignette | `macsmc-battery` sysfs, `macarchy-battery-limit`, `omarchy capture screenshot` puis surveillance du dossier de captures → vignette + Copier / Ouvrir / Supprimer (10 s) |
| `workspaces` | scrubber des workspaces occupés avec l'icône Papirus de leur première fenêtre, le courant marqué | Hyprland IPC (events + `workspaces`, `clients`) |
| `notifications` | scène : icône Papirus de l'app, résumé, corps ellipsé, ✕ | `dbus-monitor` sur `org.freedesktop.Notifications` (le mécanisme actuel), priorité 30, 5 s |
| `omarchy` | menu, clipboard (scrubber cliphist), emoji (scrubber), theme | `omarchy menu`, `cliphist list`, table d'emoji embarquée |
| `agent` | button (badge « attend ») ; scène permission (priorité 70) | hooks Claude Code, voir ci-dessous |
| `idle` | rien de visible : sur barre éteinte, fait traverser le poisson de Jarvis toutes les 10–22 min | lit les planches de `~/.local/share/jarvis/sprites` si présentes |

Module **externe** : `macarchy.jarvis` (`~/Work/jarvis/plugin/touchbar.py`).

## Scène Jarvis

- **Au repos** : `macarchy.jarvis.fish` est un Button portant le sprite idle
  à 40 px, avec ses émotions (le service QML et lui lisent le même état).
  `tap` = `omarchy-jarvis press` ; `long-press` = `omarchy-shell
  macarchy.control-center jarvis`.
- **IPC** : `macarchy-touchbar macarchy.jarvis state <idle|listening|thinking|
  speaking|followup|sleeping>`, `heard <texte>`, `reply <phrase>`, `level
  <0..1>`, `emote <nom>`. Le FSM de `bin/jarvis` les appelle là où il appelle
  aujourd'hui `set_state` et l'USR1 ; le wake daemon publie `level` à 10 Hz
  pendant `listening`.
- **`listening`** : la scène (priorité 50) prend la barre. Sprite listening à
  54 px à gauche, vumètre à bandes au centre, « J'écoute… », ✕ à droite =
  `omarchy-jarvis cancel`. Sans `level` depuis 300 ms (wake daemon arrêté,
  ce qui est le cas aujourd'hui), le vumètre bat doucement tout seul plutôt
  que de rester plat.
- **`thinking`** : le transcrit s'écrit en machine à écrire (40 car./s), trois
  points battent à droite.
- **`speaking`** : la réponse se tape phrase par phrase au rythme des `reply`,
  défilement quand elle dépasse ; ✕ = `press` (barge-in).
- **`followup`** : la scène reste, le vumètre revient en discret.
- **Fin** (`idle`) : la scène reste 4 s puis se retire ; un tap hors ✕ la
  ferme aussitôt.
- **`sleeping`** : le bouton porte le sprite sleeping ; pas de scène.

## Module agent (Claude Code)

- `install.sh` ajoute à `~/.claude/settings.json` deux hooks vers
  `macarchy-touchbar-agent` (livré dans `bin/`) :
  - `PermissionRequest` → `macarchy-touchbar-agent ask` : envoie au daemon
    l'outil, un résumé d'une ligne (commande, fichier) et l'id de session, puis
    **attend la décision** sur la socket (60 s). Sortie : la décision au format
    attendu par le hook (`allow` / `deny`), ou rien pour rendre la main au
    terminal, qui demande comme d'habitude.
  - `Notification` (attend une entrée) et `Stop` → `macarchy-touchbar-agent
    notify <événement>` : badge sur le bouton agent, clignotement « terminé ».
- La scène (priorité 70, non `dismissable`) montre l'icône de l'agent, `Bash ·
  git push origin main` ellipsé, et **Autoriser / Toujours / Refuser**.
  « Toujours » renvoie `allow` plus la règle de permission à ajouter ; le
  format exact (`updatedPermissions`) est à confirmer contre la documentation
  des hooks au moment de l'implémentation, et « Toujours » se dégrade en
  « Autoriser » s'il n'existe pas.
- Plusieurs sessions : file d'attente par id de session, une scène à la fois,
  le badge porte le compte.
- Sans daemon (barre éteinte, service arrêté), le hook rend la main
  immédiatement : rien ne bloque jamais Claude Code.

## Migration

`install.sh` fait, dans l'ordre, et est rejouable :

1. Paquets : `papirus-icon-theme`, `python-cairo`, `python-gobject`, `cava`,
   `playerctl` (vérifie, n'installe que ce qui manque, aarch64 oblige).
2. Police Material Symbols Rounded dans `~/.local/share/fonts/`, `fc-cache`.
3. Groupe `video` pour l'utilisateur ; règle udev `/dev/uinput` → `input`
   (via `pkexec`, une seule invite).
4. `systemctl disable --now tiny-dfr && systemctl mask tiny-dfr`.
5. Symlink `~/.local/bin/macarchy-touchbar`, unité user, `systemctl --user
   enable --now macarchy-touchbar`.
6. `~/.config/macarchy-touchbar/layouts.toml` s'il n'existe pas.
7. Hooks Claude Code dans `~/.claude/settings.json` (fusion, jamais
   d'écrasement).
8. Retrait des binds F13–F24 de `~/.config/hypr/bindings.lua` et de
   l'autostart `macarchy-touchbar` ; ajout du `systemctl --user start`.

Ailleurs :

- `~/Work/jarvis` : `bin/jarvis` appelle l'IPC macarchy-touchbar à la place de
  l'USR1 ; le manifeste gagne le kind ; `plugin/touchbar.py` ; le wake daemon
  publie `level` ; `HEARTBEAT_PROMPT.md` sonde `macarchy-touchbar status` au lieu
  de `pgrep`.
- `~/Work/macarchy-core` : `hardware/macarchy-touchbar` et `examples/macarchy-touchbar.layouts.toml`
  retirés, README pointe vers macarchy-touchbar.
- `install.sh --uninstall` : arrête et retire l'unité, démasque et relance
  tiny-dfr, retire les hooks. Les fichiers de config restent.

## Vérification

Je ne vois pas la barre : tout ce qui est visuel doit être lisible en PNG, et
tout ce qui est logique doit tourner sans matériel.

- `macarchy-touchbar screenshot <png>` : la scène paysage courante en PNG, lue
  après chaque changement visuel (la boucle capture → lire → corriger des
  sprites de Jarvis).
- `macarchy-touchbar touch x,y [x2,y2] [--long]` : injecte un tap, un drag ou un
  appui long dans le reconnaisseur, exactement comme event3.
- `--headless` : moteur et modules sans DRM ni evdev, sur une surface cairo en
  mémoire ; c'est le mode des tests.
- `tests/` en pytest, hors matériel : reconnaisseur de gestes (séquences
  d'événements → gestes), distribution des largeurs (mesures → rectangles,
  jamais de chevauchement), composition TOML (références, repli, erreurs),
  pile de scènes (priorités, timeouts, dismiss), chargement d'un module en
  panne (⚠ sans casser la barre), hook agent sans daemon (rend la main).
- Sur la machine, après chaque lot : `systemctl --user status macarchy-touchbar`,
  un screenshot par layout et par scène, un drag sur le slider de luminosité
  vérifié dans sysfs.

## Lots (pour le plan)

1. **Socle** : moteur (DRM, tactile, uinput, boucle), toolkit sans Scrubber,
   contrat, `core` + `display` + `system` (batterie, verrou) + `notifications`,
   layouts.toml v2, install/uninstall, tests, migration des binds. La barre
   redevient au moins ce qu'elle est aujourd'hui, en mieux dessinée, avec
   sliders et groupes qui restent ouverts.
2. **Jarvis** : `plugin/touchbar.py`, IPC depuis le FSM, `level` du wake
   daemon, scène complète.
3. **Média** : Now Playing, HUD volume/luminosité, spectre.
4. **Scrubber** : le widget, puis workspaces, emoji, presse-papier.
5. **Agent** : hooks, scène permission, badge.
6. **Finitions** : vignette de capture, `idle`, retrait d'macarchy-touchbar dans
   macarchy-core, notes de mémoire.

## Hors périmètre

- Actions de notification sur la barre.
- Un rendu par Hyprland/QML de la barre (spike non tenté, risque jugé trop
  haut).
- Multi-doigts : un seul doigt est reconnu.
- Retour haptique : le matériel n'en a pas.
