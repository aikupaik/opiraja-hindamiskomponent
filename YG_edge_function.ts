import { createClient } from "https://esm.sh/@supabase/supabase-js";
import { GoogleGenAI } from "https://esm.sh/@google/genai";

export default {
  async fetch(req: Request) {
    console.log("FUNKTSIOON KÄIVITUS: Päring jõudis kohale!");

    let tellimus_id = null;
    let supabase = null;

    try {
      const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
      const supabaseAnonKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
      supabase = createClient(supabaseUrl, supabaseAnonKey);

      console.log("Hakkan lugema sissetulevat payloadit...");
      try {
        const payload = await req.json();
        console.log("Payload edukalt loetud:", JSON.stringify(payload));
        tellimus_id = payload.record?.id;
      } catch (jsonError) {
        console.error("VIGA: Päringu JSON-i lugemine ebäonnestus või oli tühi!", jsonError.message);
        return Response.json({ error: "Vigane JSON" }, { status: 400 });
      }

      if (!tellimus_id) {
        console.error("VIGA: Payloadist ei leitud record.id-d!");
        return Response.json({ error: "Tellimuse ID puudub" }, { status: 400 });
      }

      console.log(`Edukalt kätte saadud ID: ${tellimus_id}. Otsin andmebaasist ootel rida...`);

      const { data: tellimus, error: tError } = await supabase
        .from("yg_tellimused")
        .select("*")
        .eq("id", tellimus_id)
        .single();

      if (tError || !tellimus) {
        console.error(`Andmebaasist ei leitud tellimust ID-ga: ${tellimus_id}`, tError);
        return Response.json({ error: "Tellimust ei leitud" }, { status: 404 });
      }

      console.log(`Rida leitud! Praegune staatus andmebaasis: ${tellimus.staatus}. Muudan staatuse -> tootmises`);

      const { error: uError } = await supabase
        .from("yg_tellimused")
        .update({ staatus: "tootmises" })
        .eq("id", tellimus_id);

      if (uError) {
        console.error("VIGA: Staatuse muutmine ebäonnestus!", uError);
      } else {
        console.log(`Tellimuse ${tellimus_id} staatus muudetud edukalt: TOOTMISES`);
      }

      const { data: repoRead, error: rError } = await supabase
        .from("repo_materjalid")
        .select("pealkiri, allika_url, sisu_tekst")
        .eq("kursus", tellimus.kursus);

      let referentTekst = "";
      if (!rError && repoRead && repoRead.length > 0) {
        const osad: string[] = [];
        for (const repo of repoRead) {
          let osaTekst = repo.sisu_tekst ?? "";
          if (repo.allika_url) {
            try {
              const controller = new AbortController();
              const id = setTimeout(() => controller.abort(), 3000);
              const res = await fetch(repo.allika_url, { signal: controller.signal });
              clearTimeout(id);
              if (res.ok) {
                osaTekst = await res.text();
              }
            } catch (_e) {
              // URL kättesaamatu - kasutame puhverdatud sisu_tekst-i
            }
          }
          if (osaTekst) {
            osad.push(`[Materjal: ${repo.pealkiri ?? "nimetu"}]\n${osaTekst}`);
          }
        }
        referentTekst = osad.join("\n\n---\n\n");
      }

      const alusmaterjalPlokk = referentTekst
        ? referentTekst
        : "(Selle kursuse kohta pole süsteemi hetkel ühtegi alusmaterjali laetud.)";

      console.log(
        referentTekst
          ? `Referentmaterjal leitud (${referentTekst.length} tähemärki).`
          : "Referentmaterjali ei leitud - AI loob ülesande oma üldteadmiste põhjal."
      );

      const emaObjekt = tellimus.graafi_ema_objekt ?? "";

      const koikSolmed: string[] = Array.isArray(tellimus.graafi_objektid)
        ? tellimus.graafi_objektid
        : [];

      if (koikSolmed.length === 0) {
        console.error("VIGA: graafi_objektid on tühi või mitte-massiiv!", tellimus.graafi_objektid);
        throw new Error("Tellimuses puuduvad sõlmed (graafi_objektid tühi)");
      }

      console.log("Valmistun Gemini API poole pöördumiseks...");
      const aiApiKey = Deno.env.get("GEMINI_API_KEY") ?? "";
      if (!aiApiKey) {
        console.error("KRIITILINE VIGA: GEMINI_API_KEY on keskkonnamuutujates tühi!");
        throw new Error("API võti puudub");
      }

      const ai = new GoogleGenAI({ apiKey: aiApiKey });
      const mudel = "gemini-3.1-flash-lite";

      const metoodilisedReeglid = `
        Sinu ülesandeks on luua valikvastusega küsimus.
        KONTEKST: Objekt on osa suuremast valdkonnast (${emaObjekt}), mis määrab terminoloogia täpse tähenduse.

        RANGED ÜLESANDE STRUKTUURINÕUDED.
        MIDA ALATI ÜLESANDE TEGEMISEL JÄRGITAKSE:
		1. Ülesande tüübi reegel: Loo AINULT valikvastustega ülesandeid (Multiple Choice), mille tüvi, stiimul ja valikvastused on teksti kujul (ei ole pilt, joonis vm graafiline objekt, ega eelda vastamisel pildi, joonise vm graafikali kasutamist)
		2. Valikvastusega ülesande osad on:
			- Juhis (nt: vali lünka sobiv sõna, lõpeta lause, vali õige variant)
			- Tüvi (ing k stem): ülesande püstitus ja/või küsimus, millele lahendaja peab vastama
			- Stiimul: mõne toimingu, seose, objekti või olukorra kirjeldus, millest vastus peab lähtuma.
			Võib olla ka väljavõte (nt 1-2 lõiku) mõnest dokumendist, artiklist, raamatust (vm allikast), mis on vastamisel aluseks.
			- Võti (ing k key): valikvastus, mis on ülesande õige vastus ja peav vastama täpselt ülesandes seatud tingimustele.
			- Distraktor (ing k distractor, foil): valikvastus, mis on ülesandele vale vastus. Ülesandes on ihnen mitu.
		3. Ülesehitus
			- Kõigil loodavatel ülesannetel on juhis, tüvi ja valikvastused (võti ja distraktorid)
			- Stiimul (ehk stiimulmaterjal) on siis kui ülesande püstitus seda eeldab.
			Näiteks:
				(a) "Loe läbi järgnevad värsid. Mida luuletaja soovis nendega öelda?"
				Ülesandes on esitatud ka värsid (stiimul), millest lähtudes tuleb välja valida õige vastus.
				(b) Vaata esitatud tõenäosuse leidmise valemit.
				Millist liiki tõenäosuse arvutamiseks see on? Ülesandes on esitatud stiimulina valem, mida vastajal tuleb klassifitseerida.
			- Ülesandel peab olema 4 valikvastust.
			- Ülesandes on nende hulgas ainult 1 võti (õige vastus).
			- Ülejäänud valikvastused on distraktorid (valed vastused).
		4. Valikvastusega ülesande tööpõhimõte:
			kompetentne vastaja oskab teiste seast õige vastuse (võtme) välja valida;
			vale valiku (distraktori valik) tegija on ebakompetentne.
		5. Kasutada võib järgmisi valikvastustega ülesande tüüpe:
			- "vali õige vastus"
			- "täida lünk"
			- "täida lüngad" (maksimaalselt on 2 lünka)
			- "lõpeta lause"
			- "vasta küsimusele".
		6. Nõuded keelekasutusele ülesandes
			- Ülesanded on eesti keeles
			- Kasutatakse selget ja arusaadavat lausestust. Ühe lause pikkus ei ületa üldjuhul 10 sõna.
			- Valikvastused, mis peavad täitma lünga lauses või lõpetama lauset, on vastavas grammatilises vormis
			- Ülesande tekstis ei kasutata topelt eitust, žargooni ega slängi.
			- Ülesanne kasutab õpiväljundile vastava valdkonnas ametlikult kehtivaid ja korrektseid termineid.
		6. Nõuded ülesande sisulisele ülesehitusele
			- ülesanne vastab õpitulemusele sisult ja kognitiivselt tasemelt (mäletamine, arusaamine, rakendamine jne).
			- ülesanne on otseselt kooskolas antud kursuse õppematerjaliga, KUI selline materjal on saadaval (vt ALUSMATERJALI kasutamise reeglid allpool).
			- ülesande püstitus ei ütle vastust ette ega anna õige vastuse leidmiseks vihjeid.
			- ülesande püstituses ja stiimulmaterjalis on olemas inimese vajalik lähteinfo.
		7. Nõuded valikuvariantidele
			- Võti on ülesandele sisu poolest ühemõtteliselt õige ja korrektselt sõnastatud vastus.
			- Võti ja distraktorid on sõnastatud enam-vähem sama pikkadena ja samas stüiilis.
			- Distraktorite hulgas pole üksikuid selgelt erandlikke või lausa absurdseid valikuvariante.
			- Võtmed peaksid tunduma vastajale niivõrd usutavad, et ta hakkab ülesannet läbi mõtlema.
		8. Skoorimine:
			- Võtme ehk õige vastuse valik annab 1 punkti,
			- Distraktori ehk vale vastuse valik annab 0 punkti
		9. Sama väljundi ja teema kohta erinevate ülesannete koostamine
			- kasuta sama tellimuse täitmisel erinevaid ülesannete tüüpe
			- varieeri kirjeldatud konteksti ja tahke, et ülesanded ei korduks.

		10. ALUSMATERJALI KASUTAMISE REEGLID (oluline):
			- Kui allpool ALUSMATERJAL sisaldab otseselt seda õpiväljundit käsitlevat sisu, TUGINE sellele rangelt - kasuta sealt terminoloogiat, käsitlusviisi ja rõhuasetusi.
			- Kui ALUSMATERJAL puudub, või ei käsitle otseselt just seda konkreetset õpiväljundit (nt õppejõud käsitleb seda teemat kursusel mõnel muul viisil, mida siin materjalis pole), on SINU KOHUS luua ülesanne enda ainealaste üldteadmiste põhjal. See EI OLE viga ega põhjus ülesande loomisest loobuda - see on oodatud ja normaalne käitumine. Ülesanne peab siiski vastama kursuse tasemele, õpiväljundi sõnastusele ja kognitiivsele tasemele.
			- Ära kunagi keeldu ülesannet loomast materjali puudumise tõttu.
      `;

      // Iga sõlme jaoks salvestame kohe pärast loomist (mitte alles kõige
      // lõpus koos) - kui midagi katki läheb poole peal, jääb juba tehtud
      // töö alles, mitte ei kao.
      const mitu_vaja_solme_kohta = tellimus.maht ?? 1;
      console.log(`Alustan ülesannete genereerimist. Sõlmi: ${koikSolmed.length}, ülesandeid sõlme kohta: ${mitu_vaja_solme_kohta}.`);

      // Ühe sõlme kogu töö (genereeri + salvesta KÕIK selle maht ülesannet
      // järjestikku - järjestikkus on siin TAHTLIK, et iga järgmine ülesanne
      // näeks sama sõlme eelmisi ülesandeid eristuvuse tagamiseks).
      async function tootleSolm(objekt: string): Promise<number> {
        console.log(`=== Sõlm: "${objekt}" ===`);
        const { data: vanadUlesanded } = await supabase
          .from("ylesandepank")
          .select("tyvi")
          .eq("graafi_objekt", objekt)
          .limit(5);

        let vanadeKontekst = vanadUlesanded && vanadUlesanded.length > 0
          ? vanadUlesanded.map(u => u.tyvi).join("\n---\n")
          : "Selle objekti kohta pole veel ülesandeid loodud.";

        let loodudArv = 0;

        // NB: varem küsiti SIIN eraldi Gemini kutsega IGA üksik ülesanne
        // (maht korda), mis saatis sama (pikka) alusmaterjali maht korda -
        // see oli otsene põhjus TPM (tokens-per-minute) kvoodi ületamisele.
        // Nüüd küsitakse KÕIK maht ülesannet ÜHE kutsega, JSON massiivina -
        // materjal saadetakse ainult 1 kord sõlme kohta, mitte maht korda.
        let ulesandedMassiiv: Record<string, unknown>[] | null = null;
        let ring = 0;
        const maxRinge = 2;
        let kvaliteetHeaksKiidetud = false;

        while (!kvaliteetHeaksKiidetud && ring < maxRinge) {
          ring++;
          const koostajaPrompt = `Sa oled tipptasemel õpitulemuste hindamise ekspert psühhomeetrias.
Loo TÄPSELT ${mitu_vaja_solme_kohta} ERINEVAT ülesannet kursusele ${tellimus.kursus}, objektile ${objekt} (valdkonnas ${emaObjekt}), kognitiivsel tasemel ${tellimus.kognitiivne_tase}.

ALUSMATERJAL:
"""
${alusmaterjalPlokk}
"""

${metoodilisedReeglid}

SENI LOODUD ÜLESANDED ERISTUVUSE TAGAMISEKS:
"""
${vanadeKontekst}
"""

VÄLJASTA TULEMUS RANGELT JÄRGMISE JSON MASSIIVINA - täpselt ${mitu_vaja_solme_kohta} elementi, igaüks erineva ülesandetüübi/lähenemisega, et need omavahel ei korduks (ära lisa ühtegi muud teksti ega markdown tähist, ainult puhas JSON massiiv):
[
  {
    "juhis": "juhise tekst",
    "tyvi": "tüve tekst",
    "stiimul": "stiimuli tekst või null kui puudub",
    "voti": "õige vastus",
    "distraktor_1": "esimene vale vastus",
    "distraktor_2": "teine vale vastus",
    "distraktor_3": "kolmas vale vastus"
  }
]`;

          try {
            const kResponse = await ai.models.generateContent({
              model: mudel,
              contents: koostajaPrompt,
              config: { responseMimeType: "application/json" }
            });
            const tekst = kResponse.text ?? "[]";
            const parsitud = JSON.parse(tekst);
            if (!Array.isArray(parsitud) || parsitud.length === 0) {
              throw new Error(`Gemini ei tagastanud oodatud massiivi (sõlm "${objekt}")`);
            }
            ulesandedMassiiv = parsitud;
            kvaliteetHeaksKiidetud = true;
          } catch (geminiError) {
            const on_kvoodiviga = geminiError?.status === 429 ||
              String(geminiError?.message ?? "").includes("RESOURCE_EXHAUSTED");
            if (on_kvoodiviga) {
              console.error(`KVOODI VIGA (sõlm "${objekt}") - EI proovita uuesti, väldime kvoodi raiskamist:`, geminiError.message);
              throw geminiError;
            }
            console.error(`VIGA koostaja päringul (sõlm "${objekt}", ring ${ring}):`, geminiError);
            if (ring >= maxRinge) throw geminiError;
          }
        }

        if (ulesandedMassiiv) {
          for (const ul of ulesandedMassiiv) {
            const { error: insError } = await supabase.from("ylesandepank").insert({
              kursus: tellimus.kursus,
              graafi_objekt: objekt,
              graafi_ema_objekt: emaObjekt,
              kognitiivne_tase: tellimus.kognitiivne_tase,
              juhis: ul.juhis,
              tyvi: ul.tyvi,
              stiimul: ul.stiimul === "Puudub" || ul.stiimul === "null" || !ul.stiimul ? null : ul.stiimul,
              voti: ul.voti,
              distraktor_1: ul.distraktor_1,
              distraktor_2: ul.distraktor_2,
              distraktor_3: ul.distraktor_3,
              skoor: 1,
              staatus: "kasutatav"
            });
            if (insError) {
              console.error(`VIGA kirjutamisel (sõlm "${objekt}"):`, insError);
            } else {
              loodudArv++;
            }
          }
        }
        console.log(`Sõlm "${objekt}" valmis: ${loodudArv}/${mitu_vaja_solme_kohta} ülesannet.`);
        return loodudArv;
      }

      // Sõlmed töödeldakse PARTIIDENA paralleelselt (mitte kõik korraga ja
      // mitte täiesti järjestikku) - see hoiab ära Edge Function'i 150s
      // ajapiiri ületamise suuremate graafide puhul (nt 12 sõlme x 3
      // ülesannet = 36 järjestikust Gemini kutset oleks kindlasti timeout'inud).
      const PARTII_SUURUS = 3;
      let kokkuLoodud = 0;
      for (let algus = 0; algus < koikSolmed.length; algus += PARTII_SUURUS) {
        const partii = koikSolmed.slice(algus, algus + PARTII_SUURUS);
        console.log(`--- Partii: sõlmed ${algus + 1}-${algus + partii.length}/${koikSolmed.length} paralleelselt ---`);
        const tulemused = await Promise.allSettled(partii.map(tootleSolm));
        for (const t of tulemused) {
          if (t.status === "fulfilled") kokkuLoodud += t.value;
          else console.error("Sõlme töötlus ebaõnnestus täielikult:", t.reason);
        }
      }

      // 8. Kontrollime LÕPUS tegelikku katvust, enne kui midagi märgime -
      // ATA rada 5 nõuab AINULT, et igal sõlmel oleks VÄHEMALT ÜKS
      // kasutatav ülesanne (mitte "kõik maht valmis"). Varem märgiti
      // 'tehtud' alati, sõltumata sellest, kui palju tegelikult õnnestus -
      // see jättis ATA arvama, et YG on oma töö teinud, ega proovinud
      // enam kunagi uuesti, isegi kui enamik sõlmi jäi katmata (kvoodi
      // ammendumise tõttu). Nüüd: kui mõni sõlm on ikka katmata, märgime
      // 'viga' - ATA (trigger_yg_kui_vaja) käivitab siis ISE uue YG
      // tellimuse ainult puuduolevate sõlmede jaoks järgmisel pollimisel.
      const { data: kaetusKontroll } = await supabase
        .from("ylesandepank")
        .select("graafi_objekt")
        .eq("staatus", "kasutatav")
        .in("graafi_objekt", koikSolmed);

      const kaetudSolmed = new Set((kaetusKontroll ?? []).map((r) => r.graafi_objekt));
      const puuduSolmed = koikSolmed.filter((s) => !kaetudSolmed.has(s));
      const loppStaatus = puuduSolmed.length === 0 ? "tehtud" : "viga";

      console.log(
        `Märgin tellimuse staatuse andmebaasis -> ${loppStaatus}. Kokku loodud: ${kokkuLoodud}/${koikSolmed.length * mitu_vaja_solme_kohta}. ` +
        `Katmata sõlmi: ${puuduSolmed.length}/${koikSolmed.length}${puuduSolmed.length > 0 ? " (" + puuduSolmed.join(", ") + ")" : ""}.`
      );
      await supabase.from("yg_tellimused").update({ staatus: loppStaatus }).eq("id", tellimus_id);

      return Response.json({
        message: `Genereeritud ${kokkuLoodud} ülesannet ${koikSolmed.length} sõlme kohta. Katmata sõlmi: ${puuduSolmed.length}.`,
        staatus: loppStaatus,
        puuduvad_solmed: puuduSolmed,
        alusmaterjal_kasutati: referentTekst.length > 0
      });

    } catch (error) {
      console.error("KRIITILINE GLOBAALNE VIGA FUNKTSIOONIS:", error.message);
      if (supabase && tellimus_id) {
        await supabase.from("yg_tellimused").update({ staatus: "viga" }).eq("id", tellimus_id);
      }
      return Response.json({ error: error.message }, { status: 500 });
    }
  }
};