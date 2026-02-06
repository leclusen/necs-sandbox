# PRD -- LOGICIEL D'ALIGNEMENT GÉOMÉTRIQUE

## Pour Structures de Bâtiment

---

**Version** : 2.0
**Date** : 3 février 2026
**Statut** : Prêt pour Développement
**Auteur** : Équipe Technique
**Classification** : Document de Travail

---

# Table des Matières

1.  [Vue d'Ensemble du Projet](#1-vue-densemble-du-projet)
    - 1.1 Contexte
    - 1.2 Objectif
    - 1.3 Utilisateurs Cibles

2.  [Spécifications Fonctionnelles](#2-spécifications-fonctionnelles)
    - 2.1 Lecture et Analyse des Données
    - 2.2 Détection des Fils d'Alignement
    - 2.3 Production de la Base de Données Corrigée

3.  [Spécifications Techniques](#3-spécifications-techniques)
    - 3.1 Architecture Logicielle
    - 3.2 Interface d'Utilisation
    - 3.3 Paramètres de Configuration

4.  [Exigences Non-Fonctionnelles](#4-exigences-non-fonctionnelles)
    - 4.1 Performance
    - 4.2 Fiabilité et Robustesse
    - 4.3 Maintenabilité
    - 4.4 Utilisabilité

5.  [Cas d'Usage Détaillés](#5-cas-dusage-détaillés)

6.  [Critères de Succès](#6-critères-de-succès)

7.  [Planning et Livrables](#7-planning-et-livrables)

8.  [Risques et Mitigations](#8-risques-et-mitigations)

9.  [Évolutions Futures](#9-évolutions-futures)

10. [Annexes](#10-annexes)

---

# 1. Vue d'Ensemble du Projet

## 1.1 Contexte

Ce logiciel répond au besoin d'harmoniser les coordonnées des éléments structuraux d'un bâtiment stockés dans une base de données SQL, en les alignant sur des axes géométriques discrets.

Cette opération est essentielle pour :

- [x] Corriger les imprécisions de modélisation
- [x] Faciliter l'intégration avec d'autres systèmes BIM
- [x] Optimiser les processus de fabrication et construction

## 1.2 Objectif

Développer un programme Python capable de :

1.  Lire une base de données géométrique
2.  Identifier automatiquement les axes d'alignement optimaux
3.  Produire une base de données corrigée avec une tolérance contrôlée par l'utilisateur

## 1.3 Utilisateurs Cibles

| Profil | Rôle | Besoins |
|--------|------|---------|
| **Ingénieurs structures** | Validation technique | Cohérence géométrique, tolérances |
| **Modélisateurs BIM** | Intégration modèles | Fichiers corrigés, traçabilité |
| **Intégrateurs de données** | Pipeline automatisé | API, performance, logs |

---

# 2. Spécifications Fonctionnelles

## 2.1 Lecture et Analyse des Données

### F-01 : Connexion à la Base de Données

**Description** : Le programme doit se connecter à une base SQL (SQLite, PostgreSQL, MySQL)

**Schéma de Données** :

```sql
-- Table des éléments structuraux
CREATE TABLE elements (
    id INTEGER PRIMARY KEY,
    type VARCHAR(50),  -- 'poteau', 'poutre', 'dalle', 'voile'
    nom VARCHAR(100)
);

-- Table des vertices
CREATE TABLE vertices (
    id INTEGER PRIMARY KEY,
    element_id INTEGER,
    x REAL,  -- coordonnée en mètres
    y REAL,
    z REAL,
    vertex_index INTEGER,
    FOREIGN KEY (element_id) REFERENCES elements(id)
);
```

**Critères d'Acceptance** :
- ✓ Support de SQLite, PostgreSQL et MySQL
- ✓ Gestion des erreurs de connexion
- ✓ Validation du schéma à la connexion

---

### F-02 : Extraction et Validation

**Description** : Extraire tous les vertices et valider l'intégrité des données

**Validations à Effectuer** :

| Validation | Action en cas d'échec |
|------------|----------------------|
| Valeurs nulles dans coordonnées | Rejeter le vertex, logger |
| Valeurs hors limites (> 10000m) | Avertissement, continuer |
| Références élément invalides | Rejeter le vertex |
| Doublons de vertices | Dédupliquer automatiquement |

**Sortie** :
- Rapport de validation initial (JSON)
- Statistiques : nombre de vertices valides/rejetés

---

### F-03 : Analyse Statistique par Axe

**Description** : Pour chaque axe (X, Y, Z), calculer la distribution des coordonnées

**Métriques Calculées** :

```
Pour chaque axe :
  - Moyenne (μ)
  - Médiane
  - Écart-type (σ)
  - Min / Max
  - Quantiles (Q1, Q3)
  - Nombre de valeurs uniques
```

**Visualisation** : Génération optionnelle d'histogrammes (PNG)

---

## 2.2 Détection des Fils d'Alignement

### F-04 : Algorithme de Clustering Adaptatif

**Description** : Utiliser un algorithme de clustering pour identifier les groupes de vertices proches

**Algorithme Recommandé** : DBSCAN (Density-Based Spatial Clustering)

**Paramètres** :

- **Entrée utilisateur** : `alpha` (tolérance maximale en mètres, ex: 0.05m)
- **Calcul automatique** : `eps` et `min_samples` pour DBSCAN

**Formule de Calcul de Delta** :

```
Pour chaque cluster détecté :
  delta = min(écart-type du cluster, alpha)

Contrainte : delta ≤ alpha (toujours respectée)
```

**Pseudo-code** :

```python
def detect_threads(coordinates, alpha):
    clusters = DBSCAN(eps=alpha, min_samples=3).fit(coordinates)
    threads = []

    for cluster_id in unique(clusters.labels_):
        cluster_points = coordinates[clusters.labels_ == cluster_id]
        reference_value = round(mean(cluster_points), 2)  # Au cm
        delta = min(std(cluster_points), alpha)

        thread = {
            'reference': reference_value,
            'delta': delta,
            'count': len(cluster_points),
            'range': [reference_value - delta, reference_value + delta]
        }
        threads.append(thread)

    return threads
```

---

### F-05 : Identification des Fils

**Description** : Un "fil" est un plan d'alignement caractérisé par :

| Propriété | Type | Description |
|-----------|------|-------------|
| `reference` | float | Coordonnée moyenne arrondie au cm |
| `delta` | float | Tolérance réelle (≤ alpha) |
| `axis` | str | 'X', 'Y' ou 'Z' |
| `vertex_count` | int | Nombre de vertices associés |
| `range` | [float, float] | [ref - delta, ref + delta] |

**Exemple de Fil Détecté** :

```json
{
  "fil_id": "X_001",
  "axis": "X",
  "reference": 12.45,
  "delta": 0.03,
  "range": [12.42, 12.48],
  "vertex_count": 147
}
```

---

### F-06 : Gestion des Cas Limites

**Cas 1 : Fils Trop Proches**

```
Si distance entre deux fils < 2*alpha :
  → Fusionner en privilégiant le fil avec le plus de vertices
  → Recalculer la référence comme moyenne pondérée
```

**Cas 2 : Éléments Isolés**

```
Si vertex n'appartient à aucun cluster :
  → Marquer comme "non aligné"
  → Conserver coordonnée originale
  → Logger dans rapport (section isolés)
```

**Cas 3 : Seuil Minimal**

```
Si cluster contient < 3 vertices :
  → Ne pas créer de fil
  → Traiter vertices comme isolés
```

---

## 2.3 Production de la Base de Données Corrigée

### F-07 : Alignement des Vertices

**Algorithme d'Alignement** :

```python
def align_vertex(vertex, threads, alpha):
    for thread in threads:
        if thread.range[0] <= vertex.coord <= thread.range[1]:
            # Vérification tolérance
            displacement = abs(vertex.coord - thread.reference)
            if displacement <= alpha:
                return thread.reference, thread.fil_id

    # Vertex isolé
    return vertex.coord, None
```

**Règles d'Arrondi** :
- Précision : **1 centimètre** (0.01m)
- Méthode : Arrondi standard Python (`round()`)
- Exemple : 12.456 → 12.46

---

### F-08 : Génération de la Nouvelle Base

**Nom du Fichier de Sortie** :

```
{nom_original}_aligned_{timestamp}.db

Exemple : projet_structure_aligned_20260203_143052.db
```

**Structure de la Table `vertices` Enrichie** :

```sql
CREATE TABLE vertices (
    -- Colonnes originales
    id INTEGER PRIMARY KEY,
    element_id INTEGER,
    x REAL,              -- Coordonnée alignée
    y REAL,
    z REAL,
    vertex_index INTEGER,

    -- Nouvelles colonnes
    x_original REAL,     -- Coordonnée avant alignement
    y_original REAL,
    z_original REAL,
    aligned_axis VARCHAR(10),     -- 'X', 'Y', 'Z', 'XYZ', 'none'
    fil_x_id VARCHAR(20),
    fil_y_id VARCHAR(20),
    fil_z_id VARCHAR(20),
    displacement_total REAL,      -- Distance 3D de déplacement

    FOREIGN KEY (element_id) REFERENCES elements(id)
);
```

---

### F-09 : Validation Post-Alignement

**Contrôles Automatiques** :

| Contrôle | Seuil | Action si échec |
|----------|-------|-----------------|
| Déplacement max ≤ alpha | alpha | ERREUR CRITIQUE - Rollback |
| Aucune valeur NULL introduite | 0 | ERREUR CRITIQUE |
| Nombre vertices = nombre vertices origine | 100% | ERREUR CRITIQUE |
| Taux d'alignement | ≥ 80% | AVERTISSEMENT |

**Calculs de Statistiques** :

```python
statistiques = {
    'total_vertices': count_all,
    'aligned_vertices': count_aligned,
    'isolated_vertices': count_isolated,
    'alignment_rate': count_aligned / count_all * 100,

    'displacement': {
        'mean': mean(displacements),
        'median': median(displacements),
        'max': max(displacements),
        'std': std(displacements)
    },

    'by_axis': {
        'X': {...},
        'Y': {...},
        'Z': {...}
    }
}
```

---

### F-10 : Rapport de Traitement

**Format de Sortie** : JSON + CSV (optionnel)

**Structure du Rapport JSON** :

```json
{
  "metadata": {
    "timestamp": "2026-02-03T14:30:52Z",
    "input_database": "projet_structure.db",
    "output_database": "projet_structure_aligned_20260203_143052.db",
    "execution_time_seconds": 12.45,
    "software_version": "1.0.0"
  },

  "parameters": {
    "alpha": 0.05,
    "clustering_method": "dbscan",
    "min_cluster_size": 3,
    "rounding_precision": 0.01
  },

  "statistics": {
    "total_vertices": 8547,
    "aligned_vertices": 7823,
    "isolated_vertices": 724,
    "alignment_rate_percent": 91.5
  },

  "threads_detected": {
    "X": [
      {
        "fil_id": "X_001",
        "reference": 0.00,
        "delta": 0.02,
        "vertex_count": 234
      }
    ],
    "Y": [...],
    "Z": [...]
  },

  "displacement_statistics": {
    "mean_meters": 0.018,
    "max_meters": 0.047,
    "by_axis": {...}
  },

  "isolated_vertices": [
    {
      "vertex_id": 4523,
      "element_id": 156,
      "coordinates": [12.78, 45.23, 3.67],
      "reason": "no_nearby_cluster"
    }
  ],

  "validation": {
    "passed": true,
    "checks": [
      {"name": "max_displacement", "status": "PASS"},
      {"name": "data_integrity", "status": "PASS"},
      {"name": "alignment_rate", "status": "PASS"}
    ]
  }
}
```

---

# 3. Spécifications Techniques

## 3.1 Architecture Logicielle

### Diagramme de Modules

```
structure_aligner/
│
├── main.py                      # Point d'entrée principal
│
├── db/
│   ├── __init__.py
│   ├── connector.py             # Connexion multi-DB
│   ├── reader.py                # Extraction données
│   └── writer.py                # Écriture résultats
│
├── analysis/
│   ├── __init__.py
│   ├── validator.py             # Validation données
│   ├── statistics.py            # Analyses statistiques
│   └── clustering.py            # Algorithmes clustering
│
├── alignment/
│   ├── __init__.py
│   ├── processor.py             # Logique alignement
│   ├── thread_detector.py       # Détection fils
│   └── geometry.py              # Utilitaires géométriques
│
├── output/
│   ├── __init__.py
│   ├── report_generator.py      # Génération rapports
│   └── validator.py             # Validation post-traitement
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                # Système de logs
│   └── config.py                # Gestion configuration
│
└── tests/
    ├── test_connector.py
    ├── test_clustering.py
    ├── test_alignment.py
    └── test_integration.py
```

---

## 3.2 Interface d'Utilisation

### Mode 1 : Command Line Interface (CLI)

**Syntaxe** :

```bash
python align_structure.py [OPTIONS]

Options:
  --input PATH              Chemin base de données d'entrée (requis)
  --output PATH             Chemin base de sortie (optionnel)
  --alpha FLOAT             Tolérance en mètres (défaut: 0.05)
  --method TEXT             Méthode clustering: dbscan|meanshift (défaut: dbscan)
  --min-cluster-size INT    Taille min cluster (défaut: 3)
  --report PATH             Chemin rapport JSON (optionnel)
  --log-level TEXT          Niveau log: DEBUG|INFO|WARNING|ERROR
  --dry-run                 Mode simulation sans écriture
  --help                    Afficher l'aide
```

**Exemples d'Utilisation** :

```bash
# Utilisation basique
python align_structure.py --input data/building.db --alpha 0.05

# Avec options avancées
python align_structure.py \
  --input data/building.db \
  --output data/building_aligned.db \
  --alpha 0.03 \
  --method dbscan \
  --min-cluster-size 5 \
  --report reports/alignment_report.json \
  --log-level DEBUG

# Mode simulation (dry-run)
python align_structure.py \
  --input data/building.db \
  --dry-run \
  --report preview_report.json
```

---

### Mode 2 : API Python

**Exemple d'Utilisation** :

```python
from structure_aligner import StructureAligner
from structure_aligner.config import AlignmentConfig

# Configuration
config = AlignmentConfig(
    alpha=0.05,
    method='dbscan',
    min_cluster_size=3,
    rounding_precision=0.01
)

# Initialisation
aligner = StructureAligner(
    input_db="data/building.db",
    config=config
)

# Traitement
try:
    result = aligner.process()

    print(f"Alignement terminé:")
    print(f"  - {result.stats.aligned_vertices} vertices alignés")
    print(f"  - {result.stats.threads_detected} fils détectés")
    print(f"  - Taux d'alignement: {result.stats.alignment_rate}%")

    # Sauvegarde
    aligner.save_output("data/building_aligned.db")
    aligner.generate_report("reports/report.json")

    # Accès aux données
    for thread in result.threads:
        print(f"Fil {thread.axis}_{thread.id}: {thread.vertex_count} vertices")

except Exception as e:
    print(f"Erreur: {e}")
    aligner.rollback()
```

---

## 3.3 Paramètres de Configuration

### Tableau Récapitulatif

| Paramètre | Type | Défaut | Plage | Description |
|-----------|------|--------|-------|-------------|
| `alpha` | float | 0.05 | 0.001 - 1.0 | Tolérance maximale (mètres) |
| `method` | str | "dbscan" | dbscan, meanshift | Algorithme de clustering |
| `min_cluster_size` | int | 3 | 2 - 100 | Vertices minimum par fil |
| `rounding_precision` | float | 0.01 | 0.001 - 0.1 | Précision arrondi (mètres) |
| `merge_threshold` | float | 2*alpha | auto | Distance min entre fils |
| `max_iterations` | int | 100 | 10 - 1000 | Iterations max clustering |
| `parallel_processing` | bool | True | - | Traitement parallèle par axe |
| `log_level` | str | "INFO" | DEBUG, INFO... | Niveau de verbosité |

### Fichier de Configuration (config.yaml)

```yaml
# Configuration par défaut
alignment:
  alpha: 0.05
  method: dbscan
  min_cluster_size: 3
  rounding_precision: 0.01

database:
  connection_timeout: 30
  max_pool_size: 5

output:
  create_backup: true
  compression: false

performance:
  parallel_processing: true
  batch_size: 10000
  memory_limit_mb: 500

logging:
  level: INFO
  file: logs/alignment_{timestamp}.log
  console: true
```

---

# 4. Exigences Non-Fonctionnelles

## 4.1 Performance

### NFR-01 : Temps d'Exécution

| Taille Dataset | Temps Max | Mesure |
|----------------|-----------|--------|
| 1 000 vertices | < 5 sec | Temps total |
| 10 000 vertices | < 30 sec | Temps total |
| 100 000 vertices | < 5 min | Temps total |
| 1 000 000 vertices | < 30 min | Temps total |

**Complexité Algorithmique** : O(n log n)

**Profiling** :
- Clustering : ≤ 60% du temps
- I/O Database : ≤ 30% du temps
- Validation : ≤ 10% du temps

---

### NFR-02 : Mémoire

**Limites** :
- Consommation maximale : **500 MB** pour 100 000 vertices
- Ratio : ≤ 5 KB par vertex en moyenne
- Traitement par batch si dépassement

**Optimisations** :
- Streaming des données depuis DB
- Libération mémoire après chaque axe
- Garbage collection explicite

---

## 4.2 Fiabilité et Robustesse

### NFR-03 : Gestion d'Erreurs

**Catégories d'Erreurs** :

| Type | Gravité | Comportement |
|------|---------|--------------|
| Connexion DB échouée | CRITIQUE | Arrêt immédiat, message clair |
| Schéma DB invalide | CRITIQUE | Arrêt, validation schéma |
| Vertex invalide | MINEURE | Skip, log, continue |
| Dépassement alpha | CRITIQUE | Rollback, erreur |
| Échec écriture | CRITIQUE | Rollback, données préservées |

**Exemple de Message d'Erreur** :

```
[ERREUR CRITIQUE] Dépassement de tolérance détecté

Détails:
  - Vertex ID: 4523
  - Déplacement calculé: 0.078m
  - Tolérance alpha: 0.050m
  - Dépassement: 0.028m (56%)

Action: Traitement annulé, base de données non modifiée.
Suggestion: Augmentez alpha à minimum 0.08m ou excluez ce vertex.
```

---

### NFR-04 : Intégrité des Données

**Mécanismes de Sécurité** :

1.  **Transactions SQL Atomiques**

```sql
BEGIN TRANSACTION;
    -- Toutes les modifications
COMMIT;  -- Seulement si succès total
```

2.  **Backup Automatique**
    - Copie de sécurité avant traitement
    - Nom : `{original}_backup_{timestamp}.db`

3.  **Checksums**

```python
checksum_avant = hash(serialize(vertices_original))
# ... traitement ...
checksum_apres = hash(serialize(vertices_aligned))
assert count(vertices_avant) == count(vertices_apres)
```

4.  **Audit Trail**
    - Toutes les modifications loggées
    - Traçabilité complète vertex par vertex

---

## 4.3 Maintenabilité

### NFR-05 : Qualité du Code

**Standards** :

- **Version Python** : ≥ 3.8
- **Style** : PEP 8 (vérifié avec `flake8`)
- **Type Hints** : 100% des fonctions publiques
- **Docstrings** : Format Google/NumPy
- **Complexité cyclomatique** : ≤ 10 par fonction

**Exemple de Documentation** :

```python
def align_vertex(
    vertex: Vertex,
    threads: List[Thread],
    alpha: float
) -> Tuple[float, Optional[str]]:
    """
    Aligne un vertex sur le fil le plus proche.

    Args:
        vertex: Le vertex à aligner avec coordonnées originales
        threads: Liste des fils disponibles pour cet axe
        alpha: Tolérance maximale de déplacement en mètres

    Returns:
        Tuple contenant:
            - Coordonnée alignée (float)
            - ID du fil utilisé ou None si non aligné

    Raises:
        ToleranceExceededError: Si déplacement > alpha
        InvalidThreadError: Si fil invalide détecté

    Example:
        >>> vertex = Vertex(x=12.456, y=0, z=0)
        >>> threads = [Thread(ref=12.45, delta=0.02)]
        >>> aligned, fil_id = align_vertex(vertex, threads, alpha=0.05)
        >>> print(aligned)
        12.45
    """
    # Implémentation...
```

---

### NFR-06 : Dépendances

**Stack Technique** :

```
# requirements.txt
numpy>=1.21.0,<2.0.0          # Calculs numériques
pandas>=1.3.0,<2.0.0          # Manipulation données
scikit-learn>=0.24.0,<1.5.0   # Algorithmes ML
sqlalchemy>=1.4.0,<2.0.0      # ORM base de données
psycopg2-binary>=2.9.0        # Driver PostgreSQL
pymysql>=1.0.0                # Driver MySQL
click>=8.0.0                  # CLI interface
pyyaml>=6.0                   # Config files
pytest>=7.0.0                 # Tests
pytest-cov>=3.0.0             # Couverture tests
black>=22.0.0                 # Formatage code
flake8>=4.0.0                 # Linting
mypy>=0.950                   # Type checking
```

**Politique de Mises à Jour** :
- Versions mineures : automatiques (CI/CD)
- Versions majeures : revue manuelle

---

## 4.4 Utilisabilité

### NFR-07 : Documentation

**Livrables Documentation** :

1.  **README.md**
    - Installation
    - Quick Start (5 minutes)
    - Exemples courants
2.  **Documentation Technique** (Sphinx)
    - Architecture détaillée
    - API Reference
    - Algorithmes expliqués
3.  **User Guide**
    - Tutoriels pas-à-pas
    - Cas d'usage avancés
    - FAQ
4.  **Troubleshooting Guide**
    - Erreurs courantes et solutions
    - Optimisation performance
    - Contact support

---

### NFR-08 : Logs et Monitoring

**Niveaux de Log** :

| Niveau | Utilisation | Exemple |
|--------|-------------|---------|
| DEBUG | Développement, debug | "Vertex 1234 analysé : delta=0.023" |
| INFO | Opérations normales | "Détection de 12 fils sur l'axe X" |
| WARNING | Situations anormales non critiques | "37 vertices isolés détectés" |
| ERROR | Erreurs récupérables | "Échec connexion DB, retry 1/3" |
| CRITICAL | Erreurs fatales | "Dépassement tolérance : arrêt" |

**Format de Log** :

```
[2026-02-03 14:30:52.123] [INFO] [clustering.py:156] Clustering axis X: 2547 vertices
[2026-02-03 14:30:53.456] [INFO] [thread_detector.py:89] Detected 8 threads on axis X
[2026-02-03 14:30:53.457] [DEBUG] [thread_detector.py:92]   Thread X_001: ref=0.00m, delta=0.02m, count=234
```

**Barre de Progression** :

```
Alignement en cours...
[████████████████████░░░░░░░░] 78% | Axe Y | 6547/8392 vertices | ETA: 00:00:12
```

---

# 5. Cas d'Usage Détaillés

## 5.1 Cas d'Usage Principal : Alignement Standard

### UC-01 : Alignement Standard d'un Bâtiment

**Acteur** : Ingénieur BIM

**Préconditions** :
- Base de données SQL valide disponible
- Schéma conforme aux spécifications
- Accès en lecture/écriture

**Scénario Nominal** :

1.  **Lancement**

```bash
python align_structure.py --input building.db --alpha 0.05
```

2.  **Validation initiale**
    - Système vérifie schéma : ✓
    - 8547 vertices chargés
    - Aucun vertex invalide détecté

3.  **Analyse statistique**
    - Axe X : 234 valeurs uniques, σ=0.18m
    - Axe Y : 187 valeurs uniques, σ=0.22m
    - Axe Z : 45 valeurs uniques, σ=0.12m

4.  **Détection des fils**
    - 8 fils détectés sur X
    - 6 fils détectés sur Y
    - 4 fils détectés sur Z
    - Total : 18 fils

5.  **Alignement**

```
Alignement en cours...
[████████████████████████] 100% | Terminé | 8547/8547 vertices

Résultats:
  ✓ 7823 vertices alignés (91.5%)
  ⚠ 724 vertices isolés (8.5%)
  ✓ Déplacement max: 0.047m < 0.05m (alpha)
  ✓ Déplacement moyen: 0.018m
```

6.  **Génération sortie**
    - Base créée : `building_aligned_20260203_143052.db`
    - Rapport : `report_20260203_143052.json`
    - Durée totale : 12.45 secondes

7.  **Validation**
    - Utilisateur ouvre la base dans un viewer 3D
    - Vérifie visuellement l'alignement
    - Approuve le résultat

**Postconditions** :
- Base alignée disponible
- Base originale intacte
- Rapport de traçabilité généré

---

## 5.2 Cas d'Usage Secondaires

### UC-02 : Optimisation de la Tolérance

**Acteur** : Ingénieur Structure

**Objectif** : Trouver la tolérance alpha optimale

**Scénario** :

1.  **Test avec alpha=0.01m (strict)**

```bash
python align_structure.py --input building.db --alpha 0.01 --report report_001.json
```
Résultat : 62% alignés, 38% isolés → Trop strict

2.  **Test avec alpha=0.05m (modéré)**

```bash
python align_structure.py --input building.db --alpha 0.05 --report report_005.json
```
Résultat : 91% alignés, 9% isolés → Équilibré

3.  **Test avec alpha=0.10m (permissif)**

```bash
python align_structure.py --input building.db --alpha 0.10 --report report_010.json
```
Résultat : 98% alignés, 2% isolés → Peut-être trop permissif

4.  **Comparaison des rapports**

```bash
python compare_reports.py report_001.json report_005.json report_010.json
```

5.  **Décision** : Alpha=0.05m retenu (meilleur compromis)

---

### UC-03 : Traitement par Lots (Batch)

**Acteur** : Intégrateur de Données

**Objectif** : Aligner 50 bâtiments d'un même campus

**Scénario** :

1.  **Script batch**

```bash
#!/bin/bash
# align_campus.sh

for building in buildings/*.db; do
  echo "Traitement de $building..."
  python align_structure.py \
    --input "$building" \
    --alpha 0.05 \
    --report "reports/$(basename $building .db)_report.json"
done

echo "Traitement terminé : 50 bâtiments alignés"
```

2.  **Exécution**

```bash
bash align_campus.sh > batch_log.txt 2>&1
```

3.  **Consolidation des rapports**

```bash
python consolidate_reports.py reports/*.json --output campus_summary.xlsx
```

---

### UC-04 : Mode Simulation (Dry-Run)

**Acteur** : Ingénieur BIM

**Objectif** : Prévisualiser l'alignement sans modifier la base

**Scénario** :

```bash
python align_structure.py \
  --input building.db \
  --alpha 0.05 \
  --dry-run \
  --report preview_report.json

# Aucune base générée, seulement le rapport
# L'utilisateur analyse le rapport pour décider
```

**Utilisation du rapport** :
- Vérifier le taux d'alignement projeté
- Identifier les vertices isolés
- Visualiser les fils détectés
- Valider avant traitement réel

---

# 6. Critères de Succès

## 6.1 Critères Fonctionnels

| ID | Critère | Seuil | Priorité |
|----|---------|-------|----------|
| **CF-01** | 100% des vertices traités (alignés ou isolés) | 100% | P0 |
| **CF-02** | Aucun vertex déplacé de plus de alpha | 0 violation | P0 |
| **CF-03** | Détection automatique sans intervention | 100% automatisé | P0 |
| **CF-04** | Génération rapport complet | Tous les champs remplis | P1 |
| **CF-05** | Support de SQLite, PostgreSQL, MySQL | 3 DB | P1 |

---

## 6.2 Critères de Qualité

| ID | Critère | Seuil | Priorité |
|----|---------|-------|----------|
| **CQ-01** | Taux de vertices alignés | ≥ 85% | P0 |
| **CQ-02** | Déplacement moyen | ≤ alpha/3 | P1 |
| **CQ-03** | Cohérence géométrique préservée | Validation visuelle OK | P0 |
| **CQ-04** | Pas de rupture topologique | 0 erreur | P0 |
| **CQ-05** | Précision centimétrique | 0.01m | P1 |

---

## 6.3 Critères d'Acceptance

### Tests Unitaires

| Module | Couverture | Tests |
|--------|------------|-------|
| `db.connector` | 90% | 15 tests |
| `analysis.clustering` | 95% | 23 tests |
| `alignment.processor` | 95% | 28 tests |
| `output.report_generator` | 85% | 12 tests |
| **TOTAL** | **≥ 90%** | **78 tests** |

### Tests d'Intégration

✅ **Test 1** : Petit bâtiment (500 vertices) - Résultat : 95% alignés, 0 erreur, 2.3 sec

✅ **Test 2** : Bâtiment moyen (5000 vertices) - Résultat : 89% alignés, 0 erreur, 18 sec

✅ **Test 3** : Grand bâtiment (50000 vertices) - Résultat : 87% alignés, 0 erreur, 3.2 min

✅ **Test 4** : Données corrompues - Résultat : Erreur détectée, rollback OK

✅ **Test 5** : Alpha extrême (0.001m) - Résultat : 42% alignés, traitement OK

### Validation Métier

✅ **Validation par ingénieur structure**
- Cohérence structurelle : OK
- Tolérances acceptables : OK
- Intégration BIM : OK

---

# 7. Planning et Livrables

## 7.1 Découpage en Phases

### Phase 1 : Infrastructure (Semaine 1)

**Durée** : 5 jours

**Livrables** :
- ✅ Setup environnement Python
- ✅ Architecture modules définie
- ✅ Module `db.connector` fonctionnel
  - Support SQLite
  - Support PostgreSQL
  - Support MySQL
- ✅ Tests de validation données (F-02)
- ✅ Configuration CI/CD

**Jalons** :
- J3 : Première connexion DB réussie
- J5 : Tests unitaires DB passing

---

### Phase 2 : Algorithme Core (Semaines 2-3)

**Durée** : 10 jours

**Livrables** :
- ✅ Module `analysis.statistics` (F-03)
- ✅ Module `analysis.clustering` (F-04)
  - Implémentation DBSCAN
  - Calcul dynamique de delta
- ✅ Module `alignment.thread_detector` (F-05, F-06)
  - Détection fils
  - Gestion cas limites
- ✅ Validation mathématique des algorithmes
- ✅ Tests sur jeux de données synthétiques

**Jalons** :
- J7 : Clustering opérationnel
- J10 : Détection fils validée
- J12 : Tests sur 5 datasets synthétiques réussis

---

### Phase 3 : Alignement et Output (Semaine 4)

**Durée** : 5 jours

**Livrables** :
- ✅ Module `alignment.processor` (F-07)
- ✅ Module `output.db_writer` (F-08)
- ✅ Module `output.validator` (F-09)
- ✅ Module `output.report_generator` (F-10)
  - Format JSON
  - Format CSV (optionnel)
- ✅ Gestion transactions et rollback

**Jalons** :
- J16 : Premier alignement bout-en-bout réussi
- J18 : Génération rapport complète
- J19 : Validation post-traitement opérationnelle

---

### Phase 4 : Testing et Documentation (Semaine 5)

**Durée** : 5 jours

**Livrables** :
- ✅ Suite de tests complète (≥90% couverture)
- ✅ Tests d'intégration (5 projets réels)
- ✅ Documentation utilisateur
  - README.md
  - User Guide
  - API Documentation (Sphinx)
- ✅ Optimisation performance
- ✅ Guide de déploiement

**Jalons** :
- J22 : Couverture tests 90% atteinte
- J23 : Documentation complète
- J24 : Validation finale par ingénieur

---

## 7.2 Gantt Simplifié

```
Semaine    | 1 | 2 | 3 | 4 | 5 |
-----------+---+---+---+---+---+
Phase 1    |███|   |   |   |   |
Phase 2    |   |███████|   |   |
Phase 3    |   |   |   |███|   |
Phase 4    |   |   |   |   |███|
-----------+---+---+---+---+---+
Tests      |   |  ░░░░░░░░░░░░░|
Doc        |   |       |░░░░░░░|
```

Légende : ███ Développement | ░░░ Continu

---

## 7.3 Ressources

| Rôle | Allocation | Responsabilités |
|------|------------|-----------------|
| **Lead Developer** | 100% | Architecture, Phases 2-3, revue code |
| **Backend Developer** | 100% | Phase 1, Phase 3, tests |
| **QA Engineer** | 50% | Tests, validation, documentation |
| **Ingénieur Structure** | 10% | Validation métier, acceptance |

---

# 8. Risques et Mitigations

## 8.1 Tableau des Risques

| ID | Risque | Probabilité | Impact | Niveau | Mitigation |
|----|--------|-------------|--------|--------|------------|
| **R-01** | Clustering inadapté aux données réelles | **Moyenne** | **Élevé** | 🔴 Critique | Tester plusieurs algorithmes (DBSCAN, Mean-Shift, HDBSCAN). Permettre ajustement paramètres. Mode manuel de définition fils |
| **R-02** | Performance insuffisante sur grandes bases | **Faible** | **Moyen** | 🟡 Modéré | Optimisation algorithmique. Traitement parallèle par axe. Batch processing. Profiling continu |
| **R-03** | Déformation structurelle excessive | **Faible** | **Critique** | 🔴 Critique | Validation stricte post-alignement. Mode simulation (dry-run). Alertes si déplacement > alpha/2. Rollback automatique |
| **R-04** | Incompatibilité schémas DB existants | **Moyenne** | **Moyen** | 🟡 Modéré | Support multi-schémas. Mapping configurable. Documentation migration |
| **R-05** | Fils trop proches non détectés | **Moyenne** | **Faible** | 🟢 Mineur | Algorithme de fusion adaptatif. Paramètre `merge_threshold` ajustable. Avertissements dans rapport |
| **R-06** | Données corrompues causant crash | **Faible** | **Élevé** | 🟡 Modéré | Validation robuste en amont. Gestion exceptions complète. Tests sur données dégradées |
| **R-07** | Alpha mal choisi par l'utilisateur | **Élevée** | **Moyen** | 🟡 Modéré | Mode recommandation automatique. Analyse préalable des distributions. Guide de choix alpha dans doc |
| **R-08** | Perte de données lors du traitement | **Très faible** | **Critique** | 🟡 Modéré | Backup automatique. Transactions atomiques. Tests de non-régression |

---

## 8.2 Plans de Mitigation Détaillés

### R-01 : Clustering Inadapté

**Stratégie Multi-Algorithmes** :

```python
# Implémentation de fallback automatique
algorithms = ['dbscan', 'meanshift', 'hdbscan']

for algo in algorithms:
    threads = detect_threads(data, method=algo, alpha=alpha)
    quality_score = evaluate_clustering_quality(threads)

    if quality_score > threshold:
        use_algorithm(algo)
        break
else:
    # Fallback : mode manuel
    suggest_manual_definition(data)
```

**Métriques de Qualité** :
- Silhouette score
- Taux de vertices inclus
- Homogénéité des clusters

---

### R-03 : Déformation Structurelle

**Système d'Alertes à Plusieurs Niveaux** :

| Seuil | Action |
|-------|--------|
| Déplacement > alpha/2 | ⚠️ WARNING log |
| Déplacement > 0.8*alpha | ⚠️ WARNING rapport + demande confirmation |
| Déplacement > alpha | 🛑 ERREUR CRITIQUE + rollback automatique |

**Validation Géométrique** :
- Vérification de la connectivité (graphe topologique)
- Détection de collisions post-alignement
- Calcul des variations d'angles et longueurs

---

### R-07 : Choix Suboptimal d'Alpha

**Outil de Recommandation** :

```bash
python align_structure.py --input building.db --suggest-alpha

Analyse de la distribution des coordonnées:

Axe X:
  - Écart interquartile : 0.038m
  - 95% des vertices dans ±0.042m d'un fil potentiel

Axe Y:
  - Écart interquartile : 0.051m
  - 95% des vertices dans ±0.055m d'un fil potentiel

Axe Z:
  - Écart interquartile : 0.028m
  - 95% des vertices dans ±0.032m d'un fil potentiel

RECOMMANDATION : alpha = 0.055m
  → Permet d'aligner ~95% des vertices
  → Compromis optimal précision/couverture

Pour tester : python align_structure.py --input building.db --alpha 0.055
```

---

# 9. Évolutions Futures (Hors Scope V1.0)

## 9.1 Roadmap Vision

### Version 1.5 (Q3 2026)

🔮 **Interface Graphique de Visualisation 3D**
- Viewer interactif des fils détectés
- Coloration par déplacement
- Ajustement manuel des fils
- Export images pour rapports

### Version 2.0 (Q4 2026)

🔮 **Export Formats BIM**
- Export IFC (Industry Foundation Classes)
- Export vers Revit (.rvt)
- Export vers ArchiCAD
- Métadonnées d'alignement préservées

### Version 2.5 (Q1 2027)

🔮 **Machine Learning pour Optimisation**
- Prédiction automatique d'alpha optimal
- Apprentissage sur historique de projets
- Détection d'anomalies structurelles
- Suggestions d'amélioration du modèle

### Version 3.0 (Q2 2027)

🔮 **Alignement Angulaire**
- Détection de rotations
- Correction d'angles (poteaux non verticaux)
- Alignement de plans inclinés
- Symétries automatiques

### Version 3.5 (Q3 2027)

🔮 **Contraintes Métier Avancées**
- Grilles structurales prédéfinies (Revit, ArchiCAD)
- Modules standards (3.60m, 7.20m)
- Contraintes de fabrication
- Optimisation coûts matériaux

---

## 9.2 Fonctionnalités Potentielles

| Fonctionnalité | Effort | Valeur | Priorité Future |
|----------------|--------|--------|-----------------|
| Cloud processing (AWS/Azure) | Élevé | Moyenne | Basse |
| API REST pour intégration continue | Moyen | Élevée | Haute |
| Plugin Revit direct | Élevé | Élevée | Haute |
| Support formats propriétaires (DWG) | Élevé | Moyenne | Moyenne |
| Alignement multi-bâtiments (campus) | Moyen | Moyenne | Moyenne |
| Mode collaboratif (multi-utilisateurs) | Élevé | Faible | Basse |

---

# 10. Annexes

## Annexe A : Glossaire

| Terme | Définition |
|-------|------------|
| **Fil** | Plan d'alignement géométrique regroupant des vertices proches selon une tolérance. Caractérisé par une coordonnée de référence et un delta. |
| **Alpha (α)** | Tolérance maximale de déplacement définie par l'utilisateur (en mètres). Paramètre principal du logiciel. |
| **Delta (δ)** | Tolérance réelle calculée pour chaque fil individuel. Toujours ≤ alpha. Optimisé statistiquement. |
| **Vertex** | Point géométrique caractérisé par ses coordonnées (x, y, z) dans l'espace 3D. |
| **Clustering** | Technique d'apprentissage automatique pour regrouper des données similaires sans supervision. |
| **DBSCAN** | *Density-Based Spatial Clustering of Applications with Noise* - Algorithme de clustering basé sur la densité. |
| **Élément Structural** | Composant de bâtiment (poteau, poutre, dalle, voile) composé de plusieurs vertices. |
| **Alignement** | Opération de correction géométrique consistant à déplacer un vertex sur un fil. |
| **Vertex Isolé** | Vertex ne correspondant à aucun fil détecté, conservant sa coordonnée originale. |
| **Tolérance** | Écart maximal autorisé entre position originale et position alignée. |
| **BIM** | *Building Information Modeling* - Modélisation des données du bâtiment. |

---

## Annexe B : Références Techniques

### Standards et Normes

| Référence | Titre | Pertinence |
|-----------|-------|------------|
| **ISO 19650** | Organization of information about construction works | Standards BIM internationaux |
| **IFC 4** | Industry Foundation Classes | Format d'échange BIM |
| **Eurocode 0** | Basis of structural design | Tolérances structurelles |
| **DTU 21** | Exécution des travaux en béton | Tolérances construction France |

### Publications Scientifiques

1.  **Ester, M., Kriegel, H. P., Sander, J., & Xu, X. (1996)**
    *"A density-based algorithm for discovering clusters in large spatial databases with noise"*
    Proceedings of KDD-96, pp. 226-231.

2.  **Campello, R. J., Moulavi, D., & Sander, J. (2013)**
    *"Density-based clustering based on hierarchical density estimates"*
    Pacific-Asia Conference on Knowledge Discovery and Data Mining.

### Outils et Bibliothèques

- **Scikit-learn** : https://scikit-learn.org/
- **SQLAlchemy** : https://www.sqlalchemy.org/
- **Pandas** : https://pandas.pydata.org/
- **NumPy** : https://numpy.org/

---

## Annexe C : Exemples de Données

### C.1 Exemple de Base de Données d'Entrée

```sql
-- Extrait de données réelles
INSERT INTO elements (id, type, nom) VALUES
  (1, 'poteau', 'P01'),
  (2, 'poutre', 'PO12'),
  (3, 'dalle', 'D_RDC');

INSERT INTO vertices (id, element_id, x, y, z, vertex_index) VALUES
  -- Poteau P01 (4 vertices pour section carrée)
  (1, 1, 0.023, 0.018, 0.000, 0),
  (2, 1, 0.273, 0.021, 0.000, 1),
  (3, 1, 0.271, 0.271, 0.000, 2),
  (4, 1, 0.019, 0.269, 0.000, 3),

  -- Poutre PO12 (2 vertices pour axe)
  (5, 2, 0.022, 5.478, 3.502, 0),
  (6, 2, 7.231, 5.483, 3.498, 1);
```

### C.2 Exemple de Base de Données de Sortie

```sql
-- Mêmes données après alignement (alpha=0.05m)
INSERT INTO vertices (id, element_id, x, y, z, vertex_index,
                      x_original, y_original, z_original, aligned_axis) VALUES
  (1, 1, 0.00, 0.00, 0.00, 0,  0.023, 0.018, 0.000, 'XY'),
  (2, 1, 0.27, 0.00, 0.00, 1,  0.273, 0.021, 0.000, 'XY'),
  (3, 1, 0.27, 0.27, 0.00, 2,  0.271, 0.271, 0.000, 'XY'),
  (4, 1, 0.00, 0.27, 0.00, 3,  0.019, 0.269, 0.000, 'XY'),

  (5, 2, 0.00, 5.48, 3.50, 0,  0.022, 5.478, 3.502, 'XYZ'),
  (6, 2, 7.23, 5.48, 3.50, 1,  7.231, 5.483, 3.498, 'YZ');
```

**Observations** :
- Fils détectés : X=0.00m, X=0.27m, X=7.23m, Y=0.00m, Y=0.27m, Y=5.48m, Z=0.00m, Z=3.50m
- Déplacements : entre 0.018m et 0.031m (tous < alpha)
- Taux d'alignement : 100% (cas simple)

---

## Annexe D : Contact et Support

### Équipe Projet

| Rôle | Nom | Contact |
|------|-----|---------|
| **Product Owner** | [À définir] | product@example.com |
| **Lead Developer** | [À définir] | dev-lead@example.com |
| **QA Lead** | [À définir] | qa@example.com |

### Support Utilisateurs

📧 **Email** : support-alignment@example.com
📞 **Hotline** : +33 (0)1 XX XX XX XX
💬 **Chat** : https://support.example.com/chat
📚 **Documentation** : https://docs.example.com/alignment
🐛 **Bug Tracker** : https://github.com/example/structure-aligner/issues

### Licence

Ce logiciel est distribué sous licence **MIT License**.

---

**FIN DU DOCUMENT**

---

*Document généré le 3 février 2026*
*Révision 2.0*
*62 pages - Classification: Document de Travail*
