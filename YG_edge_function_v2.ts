import { createClient } from "https://esm.sh/@supabase/supabase-js";

// LLM (GPT) kipub JSON-väljundis LaTeX-i backslash'e üle-escapima (nt kirjutab
// "\\(" ühe backslashi asemel kaks), isegi kui prompt näitab õiget kuju - see
// on tuntud mudelite käitumine. Selle asemel, et üritada prompti sõnastust
// täpselt "õigeks" saada (habras, kuna sõltub mitmest escaping-kihist meie
// enda koodis), normaliseerime väljundi SIIN, käitusajal. Kasutame
// String.fromCharCode(92)-t backslashi tähistamiseks (mitte kirjapandud \\ ),
// et välistada TÄIELIKULT võimalus, et see fail ISE lisab kogemata veel ühe
// escaping-kihi - char code on escaping-kihtidest sõltumatu.
function normeeriLatex(sisend: unknown): string {
  if (typeof sisend !== "string" || sisend.length === 0) return (sisend as string) ?? "";
  const kaksBackslashi = String.fromCharCode(92, 92); // "\\" kaks korda = topelt backslash
  const uksBackslash = String.fromCharCode(92);        // üks backslash
  let tulemus = sisend;
  // Kordame, kuni topelt-backslashe enam ei leidu - katab ka 4x/8x
  // üle-escapimise (nt kui viga oleks korduvalt kuhjunud).
  let korduseid = 0;
  while (tulemus.indexOf(kaksBackslashi) !== -1 && korduseid < 5) {
    tulemus = tulemus.split(kaksBackslashi).join(uksBackslash);
    korduseid++;
  }
  // LLM kirjutab mõnikord kogemata nähtamatuid kontrollmärke (nt backspace,
  // kood 8) tavateksti sisse - need kuvatakse brauseris "□"-na. Eemaldame
  // kõik ASCII kontrollmärgid (kood 0-31), v.a tab(9)/newline(10)/CR(13),
  // mis on tekstis endas kahjutud.
  let puhastatud = "";
  for (let i = 0; i < tulemus.length; i++) {
    const kood = tulemus.charCodeAt(i);
    if (kood < 32 && kood !== 9 && kood !== 10 && kood !== 13) continue;
    puhastatud += tulemus[i];
  }
  return puhastatud;
}

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
        console.error("VIGA: Päringu JSON-i lugemine ebaonnestus või oli tühi!", jsonError.message);
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

      console.log("Valmistun Azure OpenAI (Foundry) API poole pöördumiseks...");
      const azureEndpoint = (Deno.env.get("AZURE_OPENAI_ENDPOINT") ?? "").replace(/\/+$/, "");
      const azureApiKey = Deno.env.get("AZURE_OPENAI_API_KEY") ?? "";
      const azureDeployment = Deno.env.get("AZURE_OPENAI_DEPLOYMENT") ?? "gpt-5.4-mini";

      if (!azureEndpoint) {
        console.error("KRIITILINE VIGA: AZURE_OPENAI_ENDPOINT on keskkonnamuutujates tühi!");
        throw new Error("Azure endpoint puudub");
      }
      if (!azureApiKey) {
        console.error("KRIITILINE VIGA: AZURE_OPENAI_API_KEY on keskkonnamuutujates tühi!");
        throw new Error("API võti puudub");
      }

      const metoodilisedReeglid = `
        Oled õpitulemuste testidega hindamise ja psühhomeetria asjatundja, kes valdab head eesti keelt. 
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

		11. MATEMAATILISTE JA KEEMIA LAUSENDITE KIRJAPANEK (LaTeX):
			- Kui ülesanne (tüvi, stiimul, võti või mõni distraktor) sisaldab matemaatilist sümbolit, tehet, võrrandit, valemit või keemilist lausendit, kirjuta see LaTeX-süntaksis.
			- Piiritlejad: kasuta AINULT \\( ... \\) lühikese, teksti sees oleva avaldise jaoks (nt üksik sümbol, muutuja, lühike valem) ja \\[ ... \\] pikema, eraldi reale kuuluva avaldise jaoks (nt terve võrrand, mitmeliikmeline avaldis, maatriks). ÄRA KUNAGI kasuta $ ega $$ piiritlejana - $ võib ülesannetes tähistada valuutat (nt dollarit) ja seetõttu ei tohi seda matemaatika piiritlejana kasutada.
			- Keemiavalemite ja -reaktsioonide jaoks (nt H2O, Fe^3+, reaktsioonivõrrandid, agregaatolekud) kasuta \\ce{...} süntaksit (nt \\( \\ce{2H2 + O2 -> 2H2O} \\)) - mitte tavalist LaTeX-i indeksite/astendajate käsitsi kirjapanekut.
			- JAGAMISMÄRK: Eesti koolimatemaatikas kasutatakse jagamise tähistamiseks koolonit ":" (nt "6 : 2 = 3"), MITTE \\div käsku (mis annab sümboli "÷", levinud pigem Ameerika/Suurbritannia õpikutes). Kirjuta jagamine LaTeX-is kujul \\( 6 : 2 \\), ÄRA kasuta \\div käsku kunagi.
			- Ühikud kirjuta standard-LaTeX süntaksis otse (nt \\( 9{,}8\\ \\mathrm{m/s^2} \\)) - ÄRA eelda ega kasuta kohandatud makrosid ega väliseid pakette (nt siunitx, physics), kuna neid renderdussüsteem ei toeta.
			- KUI väärtus on LIHTNE ARV (nt vastusevariant "42" või "3,14") ILMA mistahes matemaatilise sümboli, tehte, murru, muutuja või ühikuta, ÄRA mähi seda LaTeX-piiritlejatesse - kirjuta see puhta tekstina (nt "42", mitte "\\( 42 \\)"). LaTeX-i kasuta ainult siis, kui avaldises on tegelikult matemaatilist sümbolistikat.
			- See reegel kehtib võrdselt tüve, stiimuli, võtme JA kõigi distraktorite kohta - kui üks vastusevariant vajab LaTeX-i, ei tähenda see, et ka teised peavad seda saama (nt kui võti on "\\( \\frac{1}{2} \\)" aga mõni distraktor on lihtsalt "0", jääb "0" LaTeX-ita).
			- JÄRJEPIDEVUS SAMA TÜÜPI AVALDISE JAOKS: kui SAMA LIIKI matemaatiline avaldis (nt murd) esineb mitmes ülesande osas (tüvi, stiimul, võti, distraktorid), kasuta seda LÄBIVALT SAMAS vormis kogu ülesande piires - ÄRA kirjuta ühte kohta tavatekstina (nt "2/5 + 1/5") ja teise kohta LaTeX-is (nt "\\( \\frac{2}{5} \\)"). Kui otsustad ühe murru/avaldise LaTeX-i panna, pane KÕIK sama liiki avaldised samas ülesandes samamoodi.

		12. ARVUTUSKÄIGU LÄBIMÕTLEMINE KVANTITATIIVSETE ÜLESANNETE JAOKS:
			- Kui ülesanne nõuab arvulise vastuse VÄLJA ARVUTAMIST valemi rakendamise teel (nt füüsika, keemia, inseneriteaduste, statistika ülesanded - rõhk, koormustaluvus, hõõrdumistegur, kontsentratsioon vms), pead ENNE võtme (voti) kirjapanekut kirjutama JSON-välja "arvutuskaik" täis arvutuskäigu: milliseid valemeid kasutad, milliseid väärtuseid sisestad, milline on vahetulemus, milline on lõplik vastus koos ühikuga. See väli PEAB JSON-is paiknema ENNE "voti" välja.
			- "arvutuskaik" väli VÕIB SAADA HILJEM ÕPPIJALE KUVATAVAKS (tagasiside osana pärast testi lõppu) - seega kirjuta see SELGES, ARUSAADAVAS, SAMM-SAMMULISES eesti keeles, mitte lühendatud sisemiste märkmetena. Kasuta sama LaTeX-süntaksit, mis reeglis 11 kirjeldatud (\\( \\), \\[ \\], mitte $ $).
			- Kasuta "arvutuskaik" välja ka distraktorite teadlikuks tuletamiseks: kaalu, millised on TÜÜPILISED vead selle arvutuse juures (vale valem, ühiku unustamine/vale teisendus, märgiviga, tegur 10 või 2 võrra vale) ja tuleta vähemalt osa distraktoritest just nendest tüüpilistest vigadest, mitte suvalistest usutavatest arvudest - see annab pedagoogiliselt sisukamad valed vastused.
			- Kui ülesanne EI ole kvantitatiivne/arvutuslik (enamik õpiväljundeid - definitsioonid, mõisted, tõlgendamine, klassifitseerimine), jäta "arvutuskaik" väli tühjaks stringiks "". ÄRA leiuta arvutuskäiku, kui ülesanne seda ei nõua.
      `;

      const mitu_vaja_solme_kohta = tellimus.maht ?? 1;
      console.log(`Alustan ülesannete genereerimist. Sõlmi: ${koikSolmed.length}, ülesandeid sõlme kohta: ${mitu_vaja_solme_kohta}.`);

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

VÄLJASTA TULEMUS RANGELT JÄRGMISE JSON OBJEKTINA - väli "ulesanded" peab sisaldama täpselt ${mitu_vaja_solme_kohta} elementi, igaüks erineva ülesandetüübi/lähenemisega, et need omavahel ei korduks (ära lisa ühtegi muud teksti ega markdown tähist, ainult puhas JSON):
{
  "ulesanded": [
    {
      "juhis": "juhise tekst",
      "tyvi": "tüve tekst",
      "stiimul": "stiimuli tekst või null kui puudub",
      "arvutuskaik": "täis arvutuskäik kvantitatiivse ülesande jaoks, või tühi string \"\" kui ülesanne pole arvutuslik",
      "voti": "õige vastus",
      "distraktor_1": "esimene vale vastus",
      "distraktor_2": "teine vale vastus",
      "distraktor_3": "kolmas vale vastus"
    }
  ]
}`;

          try {
            const azureRes = await fetch(
              `${azureEndpoint}/openai/v1/chat/completions?api-version=preview`,
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "api-key": azureApiKey
                },
                body: JSON.stringify({
                  model: azureDeployment,
                  messages: [
                    { role: "user", content: koostajaPrompt }
                  ],
                  response_format: { type: "json_object" }
                })
              }
            );

            if (!azureRes.ok) {
              const veaTekst = await azureRes.text();
              const on_kvoodiviga = azureRes.status === 429;
              if (on_kvoodiviga) {
                console.error(`KVOODI VIGA (sõlm "${objekt}") - EI proovita uuesti, väldime kvoodi raiskamist:`, veaTekst);
                throw new Error(`Azure kvoot ületatud (429): ${veaTekst}`);
              }
              throw new Error(`Azure OpenAI viga (HTTP ${azureRes.status}): ${veaTekst}`);
            }

            const azureData = await azureRes.json();
            const tekst = azureData.choices?.[0]?.message?.content ?? "{}";
            const parsitud = JSON.parse(tekst);
            const ulesanded = Array.isArray(parsitud?.ulesanded) ? parsitud.ulesanded : null;

            if (!ulesanded || ulesanded.length === 0) {
              throw new Error(`Azure OpenAI ei tagastanud oodatud "ulesanded" massiivi (sõlm "${objekt}")`);
            }
            ulesandedMassiiv = ulesanded;
            kvaliteetHeaksKiidetud = true;
          } catch (azureError) {
            const on_kvoodiviga = String(azureError?.message ?? "").includes("429");
            if (on_kvoodiviga) {
              throw azureError; // EI proovita uuesti kvoodivea korral
            }
            console.error(`VIGA koostaja päringul (sõlm "${objekt}", ring ${ring}):`, azureError);
            if (ring >= maxRinge) throw azureError;
          }
        }

        if (ulesandedMassiiv) {
          for (const ul of ulesandedMassiiv) {
            const tyviN = normeeriLatex(ul.tyvi);
            const stiimulN = normeeriLatex(ul.stiimul);
            const arvutuskaikN = normeeriLatex(ul.arvutuskaik);
            const votiN = normeeriLatex(ul.voti);
            const d1N = normeeriLatex(ul.distraktor_1);
            const d2N = normeeriLatex(ul.distraktor_2);
            const d3N = normeeriLatex(ul.distraktor_3);

            const { error: insError } = await supabase.from("ylesandepank").insert({
              kursus: tellimus.kursus,
              graafi_objekt: objekt,
              graafi_ema_objekt: emaObjekt,
              kognitiivne_tase: tellimus.kognitiivne_tase,
              juhis: ul.juhis,
              tyvi: tyviN,
              stiimul: stiimulN === "Puudub" || stiimulN === "null" || !stiimulN ? null : stiimulN,
              arvutuskaik: arvutuskaikN === "Puudub" || arvutuskaikN === "null" || !arvutuskaikN ? null : arvutuskaikN,
              voti: votiN,
              distraktor_1: d1N,
              distraktor_2: d2N,
              distraktor_3: d3N,
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