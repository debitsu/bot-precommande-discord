import discord
from discord import app_commands
import os
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

TOKEN = os.getenv("TOKEN")
SPREADSHEET_ID = "1BKNIai_ofjBVaKlYte6ACotQeWmOat_ZC2y9mkJ7tOk"

ALLOWED_ROLE_NAMES = {"staff"}

SHEET_NAMES = [
    "Individual",
    "Group of 5",
    "Group of 10",
    "1 clan",
    "2 clans",
    "3 clans",
    "Global",
]

CLAN_SHEETS = ["1 clan", "2 clans", "3 clans"]
CLANS_OUTPUT_SHEET = "CLANS"

LIMITES_CLAN = {
    "1 clan": 50,
    "2 clans": 100,
    "3 clans": 150,
}

OBJECTIF_TOTAL = 7000

PRODUCT_MAP = {
    "gorgon": (True, False),
    "imp": (False, True),
    "imp+gorgon": (True, True),
}

intents = discord.Intents.default()
intents.guilds = True


class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


client = MyClient()


def user_is_admin_or_staff(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.user:
        return False

    member = interaction.user

    if getattr(member.guild_permissions, "administrator", False):
        return True

    user_role_names = {role.name.lower() for role in getattr(member, "roles", [])}
    return any(role_name in user_role_names for role_name in ALLOWED_ROLE_NAMES)


def get_sheets_service():
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON manquant")

    creds_dict = json.loads(credentials_json)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    return build("sheets", "v4", credentials=creds)


def lire_lignes(sheet_name):
    service = get_sheets_service()
    range_name = f"{sheet_name}!A:I"

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()

    return result.get("values", [])


def convertir_bool(valeur):
    texte = str(valeur).strip().upper()
    return texte in ["TRUE", "VRAI", "1", "YES"]


def parser_produit(gorgon_val, imp_val):
    gorgon = convertir_bool(gorgon_val)
    imp = convertir_bool(imp_val)

    if gorgon and imp:
        return "combo"
    if gorgon:
        return "gorgon"
    if imp:
        return "imp"
    return None


def convertir_prix(prix_str):
    prix_str = str(prix_str).strip().lower()
    prix_str = prix_str.replace("$", "")
    prix_str = prix_str.replace("€", "")
    prix_str = prix_str.replace(" ", "")
    prix_str = prix_str.replace(",", ".")

    try:
        return float(prix_str)
    except ValueError:
        return 0.0


def recuperer_donnees_sheet_simple(sheet_name):
    lignes = lire_lignes(sheet_name)

    categories = {
        "gorgon": [],
        "imp": [],
    }

    total_prix = 0.0

    for ligne in lignes[1:]:
        discord_id = ligne[0].strip() if len(ligne) > 0 else ""
        hrid = ligne[1].strip() if len(ligne) > 1 else ""
        gorgon_val = ligne[2].strip() if len(ligne) > 2 else ""
        imp_val = ligne[3].strip() if len(ligne) > 3 else ""
        prix = ligne[4].strip() if len(ligne) > 4 else ""
        payment = ligne[5].strip() if len(ligne) > 5 else ""
        date_val = ligne[6].strip() if len(ligne) > 6 else ""
        game_id = ligne[7].strip() if len(ligne) > 7 else ""
        clan_val = ligne[8].strip() if len(ligne) > 8 else ""

        produit = parser_produit(gorgon_val, imp_val)

        if not discord_id and not hrid and not game_id and not clan_val:
            continue

        joueur = {
            "discord_id": discord_id or "Inconnu",
            "hrid": hrid or "Inconnu",
            "prix": prix,
            "payment": payment,
            "date": date_val,
            "game_id": game_id,
            "clan": clan_val
        }

        if produit == "gorgon":
            categories["gorgon"].append(joueur)
        elif produit == "imp":
            categories["imp"].append(joueur)
        elif produit == "combo":
            categories["gorgon"].append(joueur)
            categories["imp"].append(joueur)

        total_prix += convertir_prix(prix)

    return categories, total_prix


def recuperer_donnees(sheet_name):
    if sheet_name == "Global":
        categories_total = {
            "gorgon": [],
            "imp": [],
        }
        total_prix_global = 0.0

        autres_onglets = [s for s in SHEET_NAMES if s != "Global"]

        for onglet in autres_onglets:
            categories, total_prix = recuperer_donnees_sheet_simple(onglet)
            categories_total["gorgon"].extend(categories["gorgon"])
            categories_total["imp"].extend(categories["imp"])
            total_prix_global += total_prix

        return categories_total, total_prix_global

    return recuperer_donnees_sheet_simple(sheet_name)


def recuperer_detail_global():
    details = []
    total_general = 0.0

    autres_onglets = [s for s in SHEET_NAMES if s != "Global"]

    for onglet in autres_onglets:
        categories, total_prix = recuperer_donnees_sheet_simple(onglet)
        details.append({
            "sheet_name": onglet,
            "total_prix": total_prix,
            "gorgon": len(categories["gorgon"]),
            "imp": len(categories["imp"]),
        })
        total_general += total_prix

    return details, total_general


def formater_joueurs(joueurs):
    if not joueurs:
        return "Aucun joueur"

    lignes = [f"**{joueur['discord_id']}** — `{joueur['hrid']}`" for joueur in joueurs]
    texte = "\n".join(lignes)

    if len(texte) > 4000:
        texte = texte[:4000] + "\n..."

    return texte


def formater_game_ids(joueurs):
    ids_list = [
        j["game_id"].strip()
        for j in joueurs
        if j.get("game_id") and j["game_id"].strip()
    ]

    if not ids_list:
        return "Aucun identifiant"

    texte = ",".join(ids_list)

    if len(texte) > 20000:
        texte = texte[:20000] + "..."

    return texte


def decouper_texte_identifiants(texte, taille_max=1000):
    morceaux = []
    courant = ""

    for element in texte.split(","):
        element = element.strip()
        if not element:
            continue

        candidat = element if not courant else f"{courant},{element}"

        if len(candidat) > taille_max:
            if courant:
                morceaux.append(courant)
            courant = element
        else:
            courant = candidat

    if courant:
        morceaux.append(courant)

    return morceaux


def creer_contenu_export_game_ids(sheet_name):
    categories, _ = recuperer_donnees(sheet_name)

    gorgon_ids = formater_game_ids(categories["gorgon"])
    imp_ids = formater_game_ids(categories["imp"])

    contenu = (
        f"GORGON\n{gorgon_ids}\n\n"
        f"IMP\n{imp_ids}\n"
    )

    return contenu


def creer_embed_categorie(sheet_name, nom_categorie, joueurs, couleur):
    titres = {
        "gorgon": "🟢 Liste Gorgon",
        "imp": "🔴 Liste Imp",
    }

    embed = discord.Embed(
        title=titres[nom_categorie],
        description=f"Onglet : **{sheet_name}**\nNombre de joueurs : **{len(joueurs)}**",
        color=couleur
    )

    texte = formater_joueurs(joueurs)

    if len(texte) <= 1024:
        embed.add_field(name="Joueurs", value=texte, inline=False)
    else:
        morceaux = []
        courant = ""

        for ligne in texte.split("\n"):
            if len(courant) + len(ligne) + 1 > 1024:
                morceaux.append(courant)
                courant = ligne
            else:
                courant = ligne if not courant else courant + "\n" + ligne

        if courant:
            morceaux.append(courant)

        for i, morceau in enumerate(morceaux[:25], start=1):
            embed.add_field(name=f"Joueurs ({i})", value=morceau, inline=False)

    embed.set_footer(text="Bot liste produits")
    return embed


def creer_embed_game_ids(sheet_name, nom_categorie, joueurs, couleur):
    titres = {
        "gorgon": "🟢 Liste Game ID Gorgon",
        "imp": "🔴 Liste Game ID Imp",
    }

    embed = discord.Embed(
        title=titres[nom_categorie],
        description=f"Onglet : **{sheet_name}**\nGame ID séparés par `,`",
        color=couleur
    )

    texte = formater_game_ids(joueurs)

    if texte == "Aucun identifiant":
        embed.add_field(name="Game ID", value=texte, inline=False)
    else:
        morceaux = decouper_texte_identifiants(texte, taille_max=1000)
        for i, morceau in enumerate(morceaux[:25], start=1):
            embed.add_field(
                name=f"Game ID ({i})",
                value=f"```{morceau}```",
                inline=False
            )

    embed.set_footer(text="Copier-coller direct")
    return embed


def creer_embed_stats_global():
    details, total_general = recuperer_detail_global()

    total_gorgon = sum(item["gorgon"] for item in details)
    total_imp = sum(item["imp"] for item in details)

    pourcentage = (total_general / OBJECTIF_TOTAL) * 100 if OBJECTIF_TOTAL > 0 else 0

    total_general_affiche = int(total_general) if total_general.is_integer() else round(total_general, 2)
    pourcentage_affiche = round(pourcentage, 2)

    embed = discord.Embed(
        title="📊 Statistiques Globales",
        description="Somme de tous les onglets hors `Global`",
        color=0x5865F2
    )

    embed.add_field(name="🟢 Total Gorgon", value=str(total_gorgon), inline=False)
    embed.add_field(name="🔴 Total Imp", value=str(total_imp), inline=False)
    embed.add_field(
        name="💰 Progression financière",
        value=f"{total_general_affiche} / {OBJECTIF_TOTAL} ({pourcentage_affiche}%)",
        inline=False
    )

    lignes_detail = []
    for item in details:
        prix = int(item["total_prix"]) if item["total_prix"].is_integer() else round(item["total_prix"], 2)
        lignes_detail.append(
            f"**{item['sheet_name']}** : {prix} (G:{item['gorgon']} / I:{item['imp']})"
        )

    texte_detail = "\n".join(lignes_detail) if lignes_detail else "Aucune donnée"

    if len(texte_detail) > 1024:
        texte_detail = texte_detail[:1000] + "\n..."

    embed.add_field(name="📂 Détail par onglet", value=texte_detail, inline=False)
    embed.set_footer(text="Bot liste produits")
    return embed


def normaliser_liste_ids(texte):
    elements = [x.strip() for x in texte.split(",") if x.strip()]
    return ",".join(elements)


def chercher_ligne_par_clan_et_produit(sheet_name, clan_recherche, produit):
    lignes = lire_lignes(sheet_name)
    clan_recherche = clan_recherche.strip().lower()

    if produit not in PRODUCT_MAP:
        return None, None

    attendu_gorgon, attendu_imp = PRODUCT_MAP[produit]

    for index, ligne in enumerate(lignes[1:], start=2):
        gorgon_val = ligne[2].strip() if len(ligne) > 2 else ""
        imp_val = ligne[3].strip() if len(ligne) > 3 else ""
        clan_val = ligne[8].strip() if len(ligne) > 8 else ""

        if clan_val.lower() != clan_recherche:
            continue

        gorgon_bool = convertir_bool(gorgon_val)
        imp_bool = convertir_bool(imp_val)

        if gorgon_bool == attendu_gorgon and imp_bool == attendu_imp:
            return index, ligne

    return None, None


def lire_game_id_par_cible(sheet_name, clan_recherche, produit):
    numero_ligne, ligne = chercher_ligne_par_clan_et_produit(sheet_name, clan_recherche, produit)
    if not numero_ligne:
        return None, None
    valeur = ligne[7].strip() if len(ligne) > 7 else ""
    return numero_ligne, valeur


def ecrire_game_id(sheet_name, numero_ligne, nouvelle_valeur):
    service = get_sheets_service()
    range_name = f"{sheet_name}!H{numero_ligne}"

    body = {"values": [[nouvelle_valeur]]}

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueInputOption="RAW",
        body=body
    ).execute()


def ajouter_game_id(sheet_name, clan_recherche, produit, nouvel_id):
    numero_ligne, valeur_actuelle = lire_game_id_par_cible(sheet_name, clan_recherche, produit)
    if not numero_ligne:
        return False, "Clan + produit introuvables dans cet onglet."

    ids_existants = [x.strip() for x in valeur_actuelle.split(",") if x.strip()]
    if nouvel_id in ids_existants:
        return False, "Cet identifiant existe déjà."

    ids_existants.append(nouvel_id)
    nouvelle_valeur = ",".join(ids_existants)
    ecrire_game_id(sheet_name, numero_ligne, nouvelle_valeur)
    return True, nouvelle_valeur


def supprimer_game_id(sheet_name, clan_recherche, produit, id_a_supprimer):
    numero_ligne, valeur_actuelle = lire_game_id_par_cible(sheet_name, clan_recherche, produit)
    if not numero_ligne:
        return False, "Clan + produit introuvables dans cet onglet."

    ids_existants = [x.strip() for x in valeur_actuelle.split(",") if x.strip()]
    if id_a_supprimer not in ids_existants:
        return False, "Cet identifiant n'existe pas dans la cellule."

    ids_existants = [x for x in ids_existants if x != id_a_supprimer]
    nouvelle_valeur = ",".join(ids_existants)
    ecrire_game_id(sheet_name, numero_ligne, nouvelle_valeur)
    return True, nouvelle_valeur


def remplacer_game_id(sheet_name, clan_recherche, produit, nouvelle_liste):
    numero_ligne, _ = lire_game_id_par_cible(sheet_name, clan_recherche, produit)
    if not numero_ligne:
        return False, "Clan + produit introuvables dans cet onglet."

    nouvelle_valeur = normaliser_liste_ids(nouvelle_liste)
    ecrire_game_id(sheet_name, numero_ligne, nouvelle_valeur)
    return True, nouvelle_valeur


def index_to_col(index):
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def collecter_game_ids_par_clan():
    donnees = {}
    progression = {}

    for sheet_name in CLAN_SHEETS:
        limite = LIMITES_CLAN[sheet_name]
        lignes = lire_lignes(sheet_name)

        for ligne in lignes[1:]:
            game_id_cell = ligne[7].strip() if len(ligne) > 7 else ""
            clan_val = ligne[8].strip() if len(ligne) > 8 else ""

            if not clan_val:
                continue

            ids = [x.strip() for x in game_id_cell.split(",") if x.strip()] if game_id_cell else []

            if clan_val not in donnees:
                donnees[clan_val] = []

            for game_id in ids:
                if game_id not in donnees[clan_val]:
                    donnees[clan_val].append(game_id)

            progression[clan_val] = {
                "sheet_name": sheet_name,
                "count": len(donnees[clan_val]),
                "limit": limite
            }

    return donnees, progression


def sync_clans_sheet():
    service = get_sheets_service()

    header_result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{CLANS_OUTPUT_SHEET}!1:1"
    ).execute()

    headers = header_result.get("values", [[]])
    headers = headers[0] if headers else []

    if not headers:
        raise ValueError("La feuille CLANS n'a pas d'en-têtes en ligne 1.")

    source_data, progression = collecter_game_ids_par_clan()

    header_map = {}
    for idx, header in enumerate(headers, start=1):
        if str(header).strip():
            header_map[str(header).strip().lower()] = idx

    clans_non_trouves = []
    colonnes_mises_a_jour = 0

    for clan_name, ids in source_data.items():
        key = clan_name.strip().lower()
        if key not in header_map:
            clans_non_trouves.append(clan_name)
            continue

        col_index = header_map[key]
        col_letter = index_to_col(col_index)

        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{CLANS_OUTPUT_SHEET}!{col_letter}2:{col_letter}1000"
        ).execute()

        if ids:
            valeurs = [[x] for x in ids]
            body = {"values": valeurs}
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{CLANS_OUTPUT_SHEET}!{col_letter}2:{col_letter}{len(ids)+1}",
                valueInputOption="RAW",
                body=body
            ).execute()

        colonnes_mises_a_jour += 1

    return {
        "clans_non_trouves": clans_non_trouves,
        "clans_sync": len(source_data),
        "colonnes_mises_a_jour": colonnes_mises_a_jour,
        "progression": progression
    }


def get_all_clan_names():
    clans = set()

    for sheet_name in CLAN_SHEETS:
        lignes = lire_lignes(sheet_name)
        for ligne in lignes[1:]:
            clan_val = ligne[8].strip() if len(ligne) > 8 else ""
            if clan_val:
                clans.add(clan_val)

    return sorted(clans, key=lambda x: x.lower())


def get_products_for_clan(clan_name):
    produits = set()
    clan_lower = clan_name.strip().lower()

    for sheet_name in CLAN_SHEETS:
        lignes = lire_lignes(sheet_name)
        for ligne in lignes[1:]:
            clan_val = ligne[8].strip() if len(ligne) > 8 else ""
            if clan_val.lower() != clan_lower:
                continue

            gorgon_val = ligne[2].strip() if len(ligne) > 2 else ""
            imp_val = ligne[3].strip() if len(ligne) > 3 else ""

            g = convertir_bool(gorgon_val)
            i = convertir_bool(imp_val)

            if g and i:
                produits.add("imp+gorgon")
            elif g:
                produits.add("gorgon")
            elif i:
                produits.add("imp")

    ordre = ["gorgon", "imp", "imp+gorgon"]
    return [p for p in ordre if p in produits]


def find_sheet_for_clan_and_product(clan_name, produit):
    attendu = PRODUCT_MAP.get(produit)
    if not attendu:
        return None

    attendu_gorgon, attendu_imp = attendu
    clan_lower = clan_name.strip().lower()

    for sheet_name in CLAN_SHEETS:
        lignes = lire_lignes(sheet_name)
        for ligne in lignes[1:]:
            clan_val = ligne[8].strip() if len(ligne) > 8 else ""
            if clan_val.lower() != clan_lower:
                continue

            g = convertir_bool(ligne[2].strip() if len(ligne) > 2 else "")
            i = convertir_bool(ligne[3].strip() if len(ligne) > 3 else "")

            if g == attendu_gorgon and i == attendu_imp:
                return sheet_name

    return None


class ListeGameIDView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_game_ids(self.sheet_name, "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur liste game id gorgon :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des Game ID.", ephemeral=True)

    @discord.ui.button(label="Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_game_ids(self.sheet_name, "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur liste game id imp :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des Game ID.", ephemeral=True)

    @discord.ui.button(label="Exporter", style=discord.ButtonStyle.secondary, emoji="📁")
    async def bouton_exporter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            contenu = creer_contenu_export_game_ids(self.sheet_name)
            fichier = discord.File(
                io.BytesIO(contenu.encode("utf-8")),
                filename=f"game_id_{self.sheet_name.lower().replace(' ', '_')}.txt"
            )
            await interaction.followup.send(
                content="📁 Export des Game ID prêt :",
                file=fichier,
                ephemeral=True
            )
        except Exception as e:
            print("Erreur export game id :", e)
            await interaction.followup.send("❌ Erreur lors de l'export des Game ID.", ephemeral=True)


class GlobalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Total Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_total_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees("Global")
            embed = creer_embed_categorie("Global", "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton total gorgon global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données globales.", ephemeral=True)

    @discord.ui.button(label="Total Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_total_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees("Global")
            embed = creer_embed_categorie("Global", "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton total imp global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données globales.", ephemeral=True)

    @discord.ui.button(label="Stat", style=discord.ButtonStyle.secondary, emoji="📊")
    async def bouton_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            embed = creer_embed_stats_global()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton stats global :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des statistiques globales.", ephemeral=True)

    @discord.ui.button(label="Game ID", style=discord.ButtonStyle.secondary, emoji="🆔")
    async def bouton_game_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = discord.Embed(
                title="🆔 Game ID globaux",
                description="Choisis une catégorie pour afficher les valeurs de la colonne Game ID cumulées.",
                color=0x5865F2
            )
            embed.add_field(
                name="Options",
                value="🟢 Gorgon\n🔴 Imp\n📁 Exporter",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=ListeGameIDView("Global"),
                ephemeral=True
            )
        except Exception as e:
            print("Erreur bouton game id global :", e)
            await interaction.response.send_message("❌ Erreur lors de l'ouverture des Game ID globaux.", ephemeral=True)


class CategoryButtonsView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Gorgon", style=discord.ButtonStyle.success, emoji="🟢")
    async def bouton_gorgon(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_categorie(self.sheet_name, "gorgon", categories["gorgon"], 0x2ecc71)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton gorgon :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données.", ephemeral=True)

    @discord.ui.button(label="Imp", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bouton_imp(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            categories, _ = recuperer_donnees(self.sheet_name)
            embed = creer_embed_categorie(self.sheet_name, "imp", categories["imp"], 0xe74c3c)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print("Erreur bouton imp :", e)
            await interaction.followup.send("❌ Erreur lors de la récupération des données.", ephemeral=True)


class SheetActionView(discord.ui.View):
    def __init__(self, sheet_name):
        super().__init__(timeout=180)
        self.sheet_name = sheet_name

    @discord.ui.button(label="Catégories", style=discord.ButtonStyle.primary, emoji="📦")
    async def bouton_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = discord.Embed(
                title="📦 Catégories",
                description=f"Onglet : **{self.sheet_name}**",
                color=0x5865F2
            )
            embed.add_field(name="Options", value="🟢 Gorgon\n🔴 Imp", inline=False)
            await interaction.response.send_message(
                embed=embed,
                view=CategoryButtonsView(self.sheet_name),
                ephemeral=True
            )
        except Exception as e:
            print("Erreur action catégories :", e)
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)


class SheetSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=sheet_name, value=sheet_name)
            for sheet_name in SHEET_NAMES
        ]
        super().__init__(
            placeholder="Choisis un onglet",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        sheet_name = self.values[0]

        embed = discord.Embed(
            title="📂 Onglet sélectionné",
            description=f"Tu as choisi **{sheet_name}**.",
            color=0x5865F2
        )

        if sheet_name == "Global":
            embed.add_field(
                name="Options disponibles",
                value="🟢 Total Gorgon\n🔴 Total Imp\n📊 Stat\n🆔 Game ID",
                inline=False
            )
            await interaction.response.send_message(
                embed=embed,
                view=GlobalView(),
                ephemeral=True
            )
        else:
            embed.add_field(name="Options disponibles", value="📦 Catégories", inline=False)
            await interaction.response.send_message(
                embed=embed,
                view=SheetActionView(sheet_name),
                ephemeral=True
            )


class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(SheetSelect())


@client.tree.command(name="menu", description="Afficher le menu des produits")
async def slash_menu(interaction: discord.Interaction):
    try:
        if not user_is_admin_or_staff(interaction):
            await interaction.response.send_message(
                "❌ Commande réservée aux administrateurs ou au rôle Staff.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📦 Menu des produits",
            description="Choisis d’abord un onglet.",
            color=0x5865F2
        )
        embed.add_field(
            name="Onglets disponibles",
            value="\n".join([f"• {name}" for name in SHEET_NAMES]),
            inline=False
        )
        embed.set_footer(text="Les résultats s'affichent en privé")

        await interaction.response.send_message(
            embed=embed,
            view=MainMenuView(),
            ephemeral=True
        )
    except Exception as e:
        print("Erreur /menu :", e)
        try:
            await interaction.response.send_message(
                "❌ Erreur lors de l'ouverture du menu.",
                ephemeral=True
            )
        except:
            pass


@client.tree.command(name="id", description="Modifier les Game ID d'un clan")
@app_commands.describe(
    action="Action à effectuer",
    clan="Nom du clan",
    produit="Produit",
    identifiant="ID à ajouter/supprimer ou liste pour set"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="sup", value="sup"),
        app_commands.Choice(name="set", value="set"),
    ],
    produit=[
        app_commands.Choice(name="gorgon", value="gorgon"),
        app_commands.Choice(name="imp", value="imp"),
        app_commands.Choice(name="imp+gorgon", value="imp+gorgon"),
    ]
)
async def slash_id(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    clan: str,
    produit: app_commands.Choice[str],
    identifiant: str
):
    try:
        if not user_is_admin_or_staff(interaction):
            await interaction.response.send_message(
                "❌ Commande réservée aux administrateurs ou au rôle Staff.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        produit_val = produit.value
        action_val = action.value
        clan = clan.strip()

        clans_existants = get_all_clan_names()
        clan_match = None

        for c in clans_existants:
            if c.lower() == clan.lower():
                clan_match = c
                break

        if not clan_match:
            await interaction.followup.send("❌ Clan introuvable dans le sheet.", ephemeral=True)
            return

        produits_disponibles = get_products_for_clan(clan_match)
        if produit_val not in produits_disponibles:
            await interaction.followup.send(
                f"❌ Le produit **{produit_val}** n'est pas disponible pour **{clan_match}**.",
                ephemeral=True
            )
            return

        sheet_name = find_sheet_for_clan_and_product(clan_match, produit_val)
        if not sheet_name:
            await interaction.followup.send("❌ Impossible de trouver l'onglet correspondant.", ephemeral=True)
            return

        if action_val == "set":
            ok, resultat = remplacer_game_id(sheet_name, clan_match, produit_val, identifiant)
        elif action_val == "add":
            ok, resultat = ajouter_game_id(sheet_name, clan_match, produit_val, identifiant)
        elif action_val == "sup":
            ok, resultat = supprimer_game_id(sheet_name, clan_match, produit_val, identifiant)
        else:
            await interaction.followup.send("❌ Action invalide.", ephemeral=True)
            return

        if ok:
            await interaction.followup.send(
                f"✅ Mise à jour réussie\n\n"
                f"Clan : **{clan_match}**\n"
                f"Onglet : **{sheet_name}**\n"
                f"Produit : **{produit_val}**\n"
                f"Action : **{action_val}**\n"
                f"Résultat : `{resultat}`",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"❌ {resultat}", ephemeral=True)

    except Exception as e:
        print("Erreur /id :", e)
        try:
            await interaction.followup.send("❌ Erreur lors de la modification du Game ID.", ephemeral=True)
        except:
            pass


@client.tree.command(name="syncclans", description="Synchroniser la feuille CLANS")
async def slash_syncclans(interaction: discord.Interaction):
    try:
        if not user_is_admin_or_staff(interaction):
            await interaction.response.send_message(
                "❌ Commande réservée aux administrateurs ou au rôle Staff.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        resultat = sync_clans_sheet()

        lignes_progression = []
        for clan_name, info in resultat["progression"].items():
            lignes_progression.append(
                f"**{clan_name}** ({info['sheet_name']}) : {info['count']} / {info['limit']}"
            )

        progression_txt = "\n".join(lignes_progression) if lignes_progression else "Aucune progression"

        message_retour = (
            f"✅ Feuille **{CLANS_OUTPUT_SHEET}** mise à jour.\n"
            f"Clans trouvés : **{resultat['clans_sync']}**\n"
            f"Colonnes mises à jour : **{resultat['colonnes_mises_a_jour']}**\n\n"
            f"📈 **Progression par clan**\n{progression_txt}"
        )

        if resultat["clans_non_trouves"]:
            message_retour += (
                "\n\n⚠️ Clans sans colonne correspondante dans CLANS : "
                + ", ".join(resultat["clans_non_trouves"])
            )

        await interaction.followup.send(message_retour, ephemeral=True)

    except Exception as e:
        print("Erreur /syncclans :", e)
        try:
            await interaction.followup.send("❌ Erreur lors de la synchronisation de la feuille CLANS.", ephemeral=True)
        except:
            pass


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")


if not TOKEN:
    raise ValueError("TOKEN manquant dans Railway")

client.run(TOKEN)