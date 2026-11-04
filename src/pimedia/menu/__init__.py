"""Menu tactile du Pi (écran 800x480) : logique sans interface ici, interface Tk dans ui.py.

config.py    réglages du menu (.env)            theme.py     couleurs et polices (themes/<nom>.yaml)
weather.py   météo Open-Meteo                    audio.py     flux PipeWire, volume, « le dernier qui joue gagne »
spectrum.py  niveaux de l'égaliseur              players.py   lecteurs MPRIS, lecteur web, radio (mpv)
system.py    applis lancées, extinction          idle.py      mise en veille de l'écran
stations.py  liste des radios                    ui.py        fenêtres Tk ; main.py assemble le tout
"""
