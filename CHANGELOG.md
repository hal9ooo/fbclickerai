# Changelog

<!-- sprint-flow:changelog — i giorni li scrive ogni notte il timer di sprint-flow
     (proxmox_doctor, deploy/sprint-flow) dai commit: non modificarli a mano. -->

Cosa è cambiato, giorno per giorno, e chi l'ha fatto. Ogni argomento indica gli
agenti che hanno fatto i commit (trailer `Agent:`); «Dal backlog» elenca le voci
tolte da `BACKLOG.md` perché fatte. Il file parte dal 2026-11-13: per la storia
precedente valgono `git log` e le note delle release.

<!-- sprint-flow:inizio 6b2c940b9317d4fb44d51b23d24e1737781ac80a -->
<!-- sprint-flow:giorni -->
<!-- sprint-flow:ultimo 91f539c14374903d019fc1f527c9a18b518a93f3 -->

## 2026-11-16
<!-- sprint-flow:giorno commit=2 testo=prod-default -->

**Pulizia del repository e script obsoleti** — opencode
- Rimosse le copie di conflitto di main.py e group_moderator.py, varianti precedenti al passaggio a RapidOCR.
- Rimossi deprecated/ e gli script del flusso macOS via scp, sostituiti dal login in-container.
- decisions_cache.json non è più versionato perché è stato di esecuzione, non codice.
- Nessuna modifica al comportamento: il cambiamento riduce confusione e script superati.

**CI senza pipeline automatica, test mantenuti** — opencode
- Rimossa l'integrazione della pipeline di dispatch automatico perché non adatta ai repository pubblici.
- Eliminati il file della pipeline e la documentazione CI-CI, con il workflow che torna scritto a mano.
- La CI continua a eseguire 12 test unittest su cache, impostazioni e movimento umano.
- L'ambiente di test resta Python 3.11 con uv.

<!-- sprint-flow:giorni-fine -->
