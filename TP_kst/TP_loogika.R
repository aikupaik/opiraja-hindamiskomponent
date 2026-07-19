# =============================================================================
# TP (Testipleier) - R loogika
#
# kmassesshalfsplit()/kmassessbayesian() kutsekuju KINNITATUD 14.07.2026
# kasutaja R-keskkonnas (vt test_kstmatrix.R) - tulemused kontrollitud ka
# käsitsi BLIM valemiga, klapivad täpselt.
# =============================================================================

library(httr)
library(jsonlite)
library(kstMatrix)  # kmassesshalfsplit(), kmassessbayesian() - vt hoiatus ülal

supabase_key <- Sys.getenv("SUPABASE_SERVICE_KEY")
supabase_url <- "https://kwwxpsrojgtziluguqkm.supabase.co/rest/v1"

# ATA baasaadress(id) - TP peab ATA-t POLLIMA (mitte ainult andmebaasi
# lugema!), kuna rada 6 (staatus 'aktiivne' üleminek) käivitub ainult
# GET /api/test/status kutse SEES, mitte iseenesest. Mitu URL-i saab
# komadega eraldada (sama muster nagu HK_admin's).

ata_base_urls <- Sys.getenv("ATA_BASE_URLS")

vali_ata_url <- function() {
  urlid <- trimws(strsplit(ata_base_urls, ",")[[1]])
  urlid <- urlid[urlid != ""]
  if (length(urlid) == 0) stop("ATA_BASE_URLS on seadistamata.")
  sub("/+$", "", sample(urlid, 1))
}

# Küsib ATA-lt staatust (see KA käivitab rada 6, kui testi YP katvus on täielik -
# pole passiivne lugemine, vaid aktiivne päring, mis ATA tööle paneb).
# NB: timeout lühendatud 30s -> 8s (15.07.2026) - pikk blokeeriv päring
# Shiny observer'i sees võib kogu sessiooni "ära tarretada" (R on ühe-lõimeline),
# mis koos madala Idle Timeout seadistusega põhjustas TP nähtamatu kinnijäämise
# (viga ei tekkinud kunagi, kuna sessioon suri väljastpoolt, mitte R koodi
# enda kaudu). Lühike timeout + 1 kordus (max ~16s kokku, varasema 30s asemel)
# tasakaalustab kiiret nähtavat viga hetkeliste võrgutõrgete talumisega (?).

kysi_ata_edenemist <- function(test_id) {
  message(sprintf("[%s] kysi_ata_edenemist() ALGUS, test_id=%s", Sys.time(), test_id))
  tulem <- tryCatch({
    res <- GET(paste0(vali_ata_url(), "/api/test/status"),
               query = list(test_id = test_id), timeout(8))
    fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
  }, error = function(e) {
    message(sprintf("[%s] kysi_ata_edenemist() 1. KATSE VIGA: %s", Sys.time(), conditionMessage(e)))
    res <- GET(paste0(vali_ata_url(), "/api/test/status"),
               query = list(test_id = test_id), timeout(8))
    fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
  })
  message(sprintf("[%s] kysi_ata_edenemist() LOPP, staatus=%s test_aktiivne=%s, viga=%s, api_versioon=%s",
                  Sys.time(),
                  if (is.null(tulem$staatus)) "NULL" else tulem$staatus,
                  if (is.null(tulem$edenemine$test_aktiivne)) "NULL" else tulem$edenemine$test_aktiivne,
                  if (is.null(tulem$viga)) "-" else tulem$viga,
                  if (is.null(tulem$api_versioon)) "PUUDUB (vana ATA kood!)" else tulem$api_versioon))
  tulem
}

# Kaardistab ATA edenemine väljad kasutajasõbralikuks progressitekstiks. Vaja peamiselt YG töö ajal.
progressi_tekst <- function(vastus) {
  e <- vastus$edenemine
  if (is.null(e) || !isTRUE(e$kst_maatriks_olemas)) return("Testi kavandatakse...")
  if (isTRUE(e$test_aktiivne)) return(NULL)  # valmis - ei näidata enam
  
  # NB: kui YG on jäädavalt ebaõnnestunud ('viga'), EI TOHI näidata igavesti
  # "Koostame ülesandeid..." - see jättis kasutaja varem lõputult ootama,
  # ilma et keegi teadnuks, et midagi on katki (leitud 15.07.2026).
  
  if (identical(e$yg_tellimus_staatus, "viga")) {
    return("VIGA")  # eristatav märgend - TP_app.R käsitleb seda eraldi
  }
  if (identical(e$yg_tellimus_esitatud, TRUE) && !isTRUE(e$yg_tellimus_taidetud)) {
    return("Koostame ülesandeid...")
  }
  "Kontrollime hindamist..."
}

if (identical(supabase_key, "")) {
  warning("SUPABASE_SERVICE_KEY keskkonnamuutuja on tühi - Supabase päringud ebaõnnestuvad.")
}

sb_auth_headers <- function() {
  add_headers("apikey" = supabase_key, "Authorization" = paste("Bearer", supabase_key))
}

sb_get <- function(path) {
  res <- GET(paste0(supabase_url, path), sb_auth_headers())
  if (status_code(res) >= 300) stop(sprintf("Supabase GET ebaõnnestus (%s): %s", path, content(res, "text")))
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

# LISATUD 19.07.2026 - kasuta seda (mitte sb_get()+sprintf+URLencode), kui
# mõni filtri VÄÄRTUS on vaba tekst (nt sõlme/õpiväljundi kirjeldus), mitte
# ainult ID/kood. Põhjus: sb_get() saab path'i, mis on KÄSITSI juba
# URLencode()-itud ja sprintf()-iga kokku pandud, ning annab selle GET()-ile
# TÄISKUJUL STRINGINA. httr parsib sellise stringi URL-i uuesti läbi
# (parse_url/build_url) ja rebuild'ib selle - risk on, et juba kord
# escape'itud märgid (nt "," -> "%2C") saavad selle protsessi käigus
# TEISE KORRA kodeeritud ("%2C" -> "%252C"), mille tulemusel jõuab
# PostgREST-ini hoopis teine string kui andmebaasis on (nt
# "Teab, mis..." asemel sõna otseses mõttes "Teab%2C mis...") - päring
# ei viska viga, lihtsalt ei leia MITTE ÜHTEGI rida, kuigi andmed on
# olemas ja õiged (nähtud 19.07.2026 "Teab, mis vahe..." sõlmega).
# httr query= parameeter väldib seda täielikult, kuna VÄÄRTUS antakse
# TOORELT ja httr kodeerib selle TÄPSELT ÜKS KORD ise.

sb_get_q <- function(tee, parameetrid) {
  res <- GET(paste0(supabase_url, tee), sb_auth_headers(), query = parameetrid)
  if (status_code(res) >= 300) stop(sprintf("Supabase GET ebaõnnestus (%s): %s", tee, content(res, "text")))
  fromJSON(content(res, "text", encoding = "UTF-8"), simplifyVector = TRUE)
}

sb_post <- function(path, body_list, prefer = "return=minimal") {
  res <- POST(paste0(supabase_url, path), sb_auth_headers(),
              add_headers("Content-Type" = "application/json", "Prefer" = prefer),
              body = toJSON(body_list, auto_unbox = TRUE, null = "null"), encode = "raw")
  if (status_code(res) >= 300) stop(sprintf("Supabase POST ebaõnnestus (%s): %s", path, content(res, "text")))
  invisible(res)
}

sb_patch <- function(path, body_list) {
  res <- PATCH(paste0(supabase_url, path), sb_auth_headers(),
               add_headers("Content-Type" = "application/json"),
               body = toJSON(body_list, auto_unbox = TRUE, null = "null"), encode = "raw")
  if (status_code(res) >= 300) stop(sprintf("Supabase PATCH ebaõnnestus (%s): %s", path, content(res, "text")))
  invisible(res)
}

# NB: LISATUD 17.07.2026 - sama muster mis api.R-is: kui PostgREST vastab
# tühja massiiviga "[]", lihtsustab jsonlite selle tavaliseks list()-iks
# (pikkus 0), millel nrow() tagastab NULL, mitte 0 - "if (nrow(x) == 0)"
# viskab siis "argument is of length zero" selle asemel, et anda selge
# stop()-i teade. Turvaline loendus ühte kohta koondatud.
n_rida <- function(x) {
  if (is.null(x)) return(0L)
  if (is.data.frame(x)) return(nrow(x))
  length(x)
}

# --- Vastusevariantide järjestus ---------------------------------------------
# Sõnalised: juhuslik järjekord. Arvulised/kuupäevalised/kellaajalised:
# kahanevalt suuruse järgi (kasutaja nõue).
on_numbriline <- function(x) {
  x <- trimws(x)
  !is.na(suppressWarnings(as.numeric(x))) ||
    grepl("^\\d{4}-\\d{2}-\\d{2}", x) ||   # kuupäev (ISO)
    grepl("^\\d{1,2}[:.]\\d{2}", x)        # kellaaeg
}

numbriline_vaartus <- function(x) {
  x <- trimws(x)
  v <- suppressWarnings(as.numeric(x))
  if (!is.na(v)) return(v)
  # Proovi kuupäeva/kellaaega numbriks teisendada järjestamise jaoks
  d <- suppressWarnings(as.POSIXct(x, tryFormats = c("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S", "%H:%M")))
  if (!is.na(d)) return(as.numeric(d))
  NA_real_
}

jarjesta_variandid <- function(voti, distraktorid) {
  koik <- c(voti, distraktorid)
  koik <- koik[!is.na(koik) & koik != ""]
  if (length(koik) > 1 && all(sapply(koik, on_numbriline))) {
    koik[order(sapply(koik, numbriline_vaartus), decreasing = TRUE)]
  } else {
    sample(koik)
  }
}

# --- Küsimuse valik (half-split) ---------------------------------------------
# KINNITATUD 14.07.2026 kasutaja R-keskkonnas: kmassesshalfsplit(probs, ks)
# tagastab veeru-indeksi (sõlme), mis jagab posterior-i kõige ühtlasemalt.
vali_jargmine_solm <- function(posterior, K) {
  kmassesshalfsplit(posterior, K)
}

# --- Bayes-uuendus ------------------------------------------------------------
# KINNITATUD 14.07.2026: kmassessbayesian(probs, ks, beta, eta, question, response)
# Tulemus kontrollitud käsitsi BLIM valemiga - klapib täpselt.
uuenda_posterior <- function(posterior, K, solm_indeks, vastus_oige, beta, eta) {
  kmassessbayesian(posterior, K, beta, eta, solm_indeks, as.integer(vastus_oige))
}

# --- Ühe sõlme jaoks vali YP ülesanne, mida veel pole selle testi sees kasutatud
# NB: pärib LIVE otse ylesandepank-ist (mitte testi_loogika salvestatud
# ühest yp_id-st), kuna ATA/YG loob 3 ülesannet sõlme kohta ja TP peab
# saama korduvvaatluse jaoks valida NEIST, mida veel pole selles testis
# kasutatud. Kasutab konkreetse valitud ülesande enda beta/eta (üksuse-
# tasandi täpsus), mitte sõlme-taseme keskmist.
#
# NB: PARANDATUD 19.07.2026 - varem filtreeriti SIIN ka kursuse järgi
# (kursus=eq.X&graafi_objekt=eq.Y), aga kasutaja täpsustas arhitektuuri:
# GRAAFI OBJEKT (sõlm) on ülesande sobivuse tegelik identiteet - kursus
# on ainult ABISTAV viide, mida YG kasutab materjali/konteksti leidmiseks
# ülesande LOOMISEL, mitte ligipääsu piirav võti selle KASUTAMISEL. Sama
# sõlme jaoks loodud ülesanne sobib IGA kursuse testile, mis seda sõlme
# küsib, sõltumata sellest, mis kursuse all see algselt loodi. Vale
# kursuse-filter siin (aga mitte ATA kontrolli_yp_katvust()-is, kus
# seda kunagi polnudki) põhjustas TP-l 0-tulemuse iga kord, kui testi
# kursuse-väli erines sellest, mille all ülesanne algselt genereeriti
# (nähtud 19.07: test kursus="sfyysika1", ülesanded kursus="fyysika2",
# sama sõlme tekst - ATA leidis katvuse õigesti, TP mitte).

vali_ylesanne_solmele <- function(solm, kysitud_yp_idd) {
  kandidaadid <- sb_get_q("/ylesandepank", list(
    graafi_objekt = paste0("eq.", solm),
    staatus = "eq.kasutatav",
    select = "yp_id,beeta_error,g_guess,kasutamiste_arv"
  ))
  if (n_rida(kandidaadid) == 0) stop(sprintf("Sõlmele '%s' ei leitud ühtegi kasutatavat ülesannet.", solm))
  
  kasutamata <- kandidaadid[!(kandidaadid$yp_id %in% kysitud_yp_idd), ]
  valik <- if (nrow(kasutamata) > 0) kasutamata[1, ] else kandidaadid[1, ]  # kõik juba küsitud - korda
  
  list(yp_id = valik$yp_id, beta = valik$beeta_error, eta = valik$g_guess,
       kasutamiste_arv = valik$kasutamiste_arv)
}

# --- Ülesande sisu laadimine ---------------------------------------------
lae_ylesanne <- function(yp_id) {
  rida <- sb_get(sprintf("/ylesandepank?yp_id=eq.%s&select=*", yp_id))
  if (n_rida(rida) == 0) stop(sprintf("Ülesannet yp_id=%s ei leitud.", yp_id))
  rida <- rida[1, ]
  list(
    yp_id = rida$yp_id,
    juhis = rida$juhis,
    tyvi = rida$tyvi,
    stiimul = if (length(rida$stiimul) == 0 || is.na(rida$stiimul)) NULL else rida$stiimul,
    voti = rida$voti,
    variandid = jarjesta_variandid(rida$voti, c(rida$distraktor_1, rida$distraktor_2, rida$distraktor_3))
  )
}

# --- Testi täieliku oleku laadimine/algatamine --------------------------------
lae_tp_seisund <- function(test_id) {
  sessioon <- sb_get(sprintf("/testisessioonid?test_id=eq.%s&select=*", test_id))
  if (n_rida(sessioon) == 0) stop("Tundmatu test_id.")
  sessioon <- sessioon[1, ]
  
  if (!identical(sessioon$staatus, "aktiivne")) {
    stop(sprintf("Test ei ole staatuses 'aktiivne' (praegu: %s).", sessioon$staatus))
  }
  
  # NB: PARANDATUD 16.07.2026 - varasem "sessioon$testi_loogika[[1]]" eeldas,
  # et väli tuleb alati tagasi pikkus-1 list-kujul, aga kui väärtus on tühi
  # ({} - nt tp_seisund uue testi puhul) või jsonlite lihtsustab selle
  # teisiti, võib [[1]] visata "subscript out of bounds". Kaitsev lugemine:
  # käsitleb nii string- (vajab fromJSON) kui juba-list-kujul tagastust,
  # ja tühja/puuduva välja korral tagastab vaikimisi tühja list().
  
  loe_jsonb_vali <- function(toores) {
    if (is.character(toores) && length(toores) >= 1) {
      return(fromJSON(toores[[1]]))
    }
    if (is.list(toores) && length(toores) >= 1) {
      return(toores[[1]])
    }
    list()
  }
  
  testi_loogika <- loe_jsonb_vali(sessioon$testi_loogika)
  tp_seisund <- loe_jsonb_vali(sessioon$tp_seisund)
  
  solmed <- testi_loogika$solmed
  K <- matrix(unlist(testi_loogika$K), nrow = length(testi_loogika$P_K), byrow = TRUE)
  colnames(K) <- solmed
  
  if (length(tp_seisund) == 0) {
    # Uus test - alusta ühtlasest priorist
    posterior <- unname(testi_loogika$P_K)
    kysitud <- list()
  } else {
    posterior <- unname(tp_seisund$posterior)
    kysitud <- tp_seisund$kysitud
  }
  
  list(
    test_id = test_id,
    metoodika = sessioon$metoodika,
    kursus = sessioon$kursus,
    testi_loogika = testi_loogika,
    solmed = solmed,
    K = K,
    posterior = posterior,
    kysitud = kysitud,  # list of list(yp_id=, solm=, vastus_oige=)
    # NB: PARANDATUD 19.07.2026 - vt vestlus "reliaablus vs adaptiivsus".
    # See väli on nüüd puhtalt INFORMATIIVNE (app.R arvutab peatumiseks
    # oma turvapiir()/reliaabluse_pohi() funktsioonidega otse, et vältida
    # kahes kohas lahkneva valemi riski) - hoitud siin samas kujus, kui
    # keegi tulevikus vajab seda väljaspool app.R konteksti.
    max_kysimusi = max(2 * length(solmed), min(max(7, ceiling(1.5 * length(solmed))), 10) + 1)
  )
}

salvesta_tp_seisund <- function(test_id, posterior, kysitud) {
  # NB: LISATUD 19.07.2026 - LEITUD JUURPÕHJUS lõpptulemuse tõsisele
  # moonutusele. kmassessbayesian() tagastab posterior-i, mille KÕIK
  # elemendid on nimetatud SAMA nimega (viimati testitud sõlme järgi, nt
  # kõik "C") - kahjutu R-i sees (väärtused/järjekord on õiged), aga
  # toJSON() serialiseerib NIMELISE vektori vaikimisi JSON OBJEKTINA, ja
  # 4 identse võtmega JSON-objektis ("C":x1,"C":x2,"C":x3,"C":x4) jääb
  # alles ainult VIIMANE - ülejäänud kolm kaovad vaikselt. Iga järgnev
  # vastus arvutas seega juba kokkuvarisenud/vale-kujulise posterior-i
  # pealt edasi, mis kogunes vastuste kaupa hullemaks (kinnitatud 19.07
  # kasutaja käsitsi jooksutatud kstMatrix jadaga, mis andis puhtal
  # in-memory kujul õige tulemuse, aga tootmises salvestatud/taasloetud
  # kuju andis täiesti teistsuguse, vale tulemuse). unname() tagab, et
  # JSON-i läheb alati puhas massiiv, mitte kokkuvarisev objekt.
  sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
    tp_seisund = toJSON(list(posterior = unname(posterior), kysitud = kysitud), auto_unbox = TRUE)
  ))
}

lopeta_test <- function(test_id, posterior, solmed, K, peatumise_pohjus,
                        tau_tagasiside = 0.9) {
  # =============================================================================
  # LISATUD 17.07.2026 - vt vestlus samal kuupäeval ("kst analüüsi ja
  # modelleerimise ekspert" arutelu). Varasem lähenemine (which.max(posterior)
  # + kmfringe ühel olekul) kasutas ainult ÜHTE, kõige tõenäolisemat olekut -
  # see ignoreeris kogu posterior-i laiust ja "valetas" kindluse kohta, kui
  # mitu olekut olid peaaegu sama tõenäolised.
  #
  # Uus lähenemine: USUTAVATE OLEKUTE HULK C (kõik olekud, mis kokku katavad
  # tau_tagasiside osa posterior massist, kahanevas tõenäosuse järjekorras),
  # ja kmfringe() rakendatud KÕIGILE C hulga olekutele, mitte ainult ühele.
  # Sõlme tasandil on 4 võimalikku tulemust:
  #   "olemas"        - sõlm kuulub KÕIKIDESSE C olekutesse (kindel omandatus)
  #   "valmis_oppima" - sõlm on väline äär KÕIKIDES C olekutes (kindel "järgmine")
  #   "veel_mitte"    - sõlm ei ole ei omandatud ega äärel MITTE üheski C
  #                     olekus (kindlalt hilisem samm, pole veel aktuaalne)
  #   "ebamaarane"     - C hulga olekud lähevad selle sõlme suhtes lahku -
  #                     AUS ebamäärasuse signaal (test ei suutnud eristada),
  #                     tekib ISEENESEST, ei vaja eraldi lävendamist
  #
  # tau_tagasiside (0.9) on TEADLIKULT rangem kui testi enda peatumislävi
  # (0.8) - tagasiside jaoks tahame kõrgemat kindlust kui testi enda
  # peatumisotsuseks piisab (vt 17.07 arutelu selle valiku kohta).
  # =============================================================================
  
  usutavad_olekud <- function(posterior, tau) {
    jarjekord <- order(posterior, decreasing = TRUE)
    kumulatiivne <- cumsum(posterior[jarjekord])
    n <- which(kumulatiivne >= tau)[1]
    if (is.na(n)) n <- length(posterior)
    jarjekord[seq_len(n)]
  }
  
  klassifitseeri_solmed <- function(K, solmed, C_indeksid) {
    olekud_info <- lapply(C_indeksid, function(i) {
      olek <- K[i, ]
      list(olek = olek, aar = kmfringe(olek, K))
    })
    klass <- character(length(solmed))
    for (j in seq_along(solmed)) {
      kuulub <- vapply(olekud_info, function(x) x$olek[j] == 1, logical(1))
      valmis <- vapply(olekud_info, function(x) x$aar[j] == 1 && x$olek[j] == 0, logical(1))
      klass[j] <- if (all(kuulub)) {
        "olemas"
      } else if (all(valmis)) {
        "valmis_oppima"
      } else if (!any(kuulub) && !any(valmis)) {
        "veel_mitte"
      } else {
        "ebamaarane"
      }
    }
    setNames(klass, solmed)
  }
  
  C <- usutavad_olekud(posterior, tau_tagasiside)
  klass <- klassifitseeri_solmed(K, solmed, C)
  
  omandatud     <- unname(names(klass)[klass == "olemas"])
  valmis_oppima <- unname(names(klass)[klass == "valmis_oppima"])
  ebamaarane    <- unname(names(klass)[klass == "ebamaarane"])
  veel_mitte    <- unname(names(klass)[klass == "veel_mitte"])
  
  # LISATUD 19.07.2026 - vt vestlus samal kuupäeval ("kaks mõõdet: sõlmede
  # järjekord ja info hulk"). "Ebamäärane" pole ühtlane kategooria - suund
  # on pedagoogiliselt oluline:
  #   ebamaarane_edasi  - sõlm on struktuuriliselt EDASI mõnest juba
  #                        omandatud sõlmest (vajab seda eeldusena) ->
  #                        ebamäärasus on OODATAV/julgustav signaal
  #                        ("andmed napid, aga loogiline järgmine samm")
  #   ebamaarane_tagasi - sõlm on struktuuriliselt EELDUS mõnele juba
  #                        omandatud sõlmele -> ebamäärasus on ÜLLATAV
  #                        (kuidas said hilisemat, kui varasem kaheldav?),
  #                        viitab juhuslikule eksimusele või ebaühtlasele
  #                        teadmisele - väärib kordustestimist
  # Eristusreegel: sõlm j on "tagasi", kui IGA kehtiv olek (kogu K-s, mitte
  # ainult C hulgas), mis sisaldab kõiki omandatud sõlmi, sisaldab ka j-d
  # (s.t. j on struktuuriliselt VAJALIK omandatud sõlmede jaoks). Muidu
  # "edasi" (omandatud sõlmed on ise j eelduseks, või pole seost).
  on_eeldus_omandatule <- function(j_indeks, omandatud_indeksid, K) {
    if (length(omandatud_indeksid) == 0) return(FALSE)
    olekud_omandatuga <- apply(K[, omandatud_indeksid, drop = FALSE], 1,
                               function(r) all(r == 1))
    if (!any(olekud_omandatuga)) return(FALSE)
    all(K[olekud_omandatuga, j_indeks] == 1)
  }
  omandatud_indeksid <- which(solmed %in% omandatud)
  ebamaarane_tagasi <- character(0)
  ebamaarane_edasi <- character(0)
  for (s in ebamaarane) {
    j <- which(solmed == s)
    if (on_eeldus_omandatule(j, omandatud_indeksid, K)) {
      ebamaarane_tagasi <- c(ebamaarane_tagasi, s)
    } else {
      ebamaarane_edasi <- c(ebamaarane_edasi, s)
    }
  }
  
  # Erijuht (Doignon & Falmagne mõttes: olek = Q, täisruum, väline äär
  # defineeritult tühi) - kui kõik sõlmed on "olemas", pole midagi enam
  # järgmisena pakkuda.
  kokkuvote <- if (length(omandatud) == length(solmed)) {
    "Teadsid kõike! Võta uus õpiväljund."
  } else if (length(valmis_oppima) + length(ebamaarane_edasi) > 1) {
    "Sul on nüüd mitu võimalikku suunda, kust jätkata - kõik sobivad järgmiseks võrdselt hästi."
  } else {
    NULL
  }
  
  lopp_profiil <- list(
    omandatud           = omandatud,
    valmis_oppima        = valmis_oppima,
    ebamaarane_edasi     = ebamaarane_edasi,
    ebamaarane_tagasi    = ebamaarane_tagasi,
    veel_mitte           = veel_mitte,
    kokkuvote            = kokkuvote,
    peatumise_pohjus     = peatumise_pohjus,
    kindlus_parim_olek   = max(posterior),
    kindlus_C_hulgas     = sum(posterior[C]),
    n_usutavaid_olekuid  = length(C)
  )
  sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list(
    staatus = "lõpetatud",
    lopp_profiil = toJSON(lopp_profiil, auto_unbox = TRUE, null = "null")
  ))
  lopp_profiil
}
