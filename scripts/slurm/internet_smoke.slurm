#!/bin/bash
#SBATCH --job-name=wikidata_sparql
#SBATCH --output=wikidata_sparql_%j.out
#SBATCH --error=wikidata_sparql_%j.err
#SBATCH --time=00:03:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=256M

set -uo pipefail
set -x   # TRACE every command (VERY useful)

echo "========== JOB START =========="
echo "Job ID      : $SLURM_JOB_ID"
echo "Node        : $(hostname)"
echo "Partition   : $SLURM_JOB_PARTITION"
echo "Start time  : $(date)"
echo

ENDPOINT="https://query.wikidata.org/sparql"
OUTFILE="wikidata_result_${SLURM_JOB_ID}.json"

echo "Endpoint    : $ENDPOINT"
echo "Output file : $OUTFILE"
echo

echo "=== NETWORK PRECHECK ==="
getent hosts query.wikidata.org || echo "DNS FAILED"
curl -I https://query.wikidata.org --max-time 5 || echo "HEAD FAILED"
echo

echo "=== BUILDING SPARQL QUERY ==="

# Temporarily allow non-zero exit for read
set +e
read -r -d '' SPARQL << 'EOF'
SELECT DISTINCT ?r2 WHERE {
  ?h wdt:P1032 ?t .
  ?t ?r2 ?c .
  ?r2entity wikibase:directClaim ?r2 ;
            wikibase:propertyType wikibase:WikibaseItem .
}
LIMIT 100
EOF
READ_RC=$?
set -e

echo "read exit code: $READ_RC"
echo "SPARQL length : ${#SPARQL}"
echo "SPARQL preview:"
echo "----------------"
echo "$SPARQL"
echo "----------------"
echo

UA="omar@gmail.com (Slurm job; contact: omar@gmail.com)"
echo "User-Agent   : $UA"
echo

echo "=== EXECUTING CURL ==="

curl -v -G "$ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  -H "User-Agent: $UA" \
  --data-urlencode "query=$SPARQL" \
  --retry 3 \
  --retry-delay 2 \
  --max-time 30 \
  -o "$OUTFILE"

CURL_RC=$?
echo "curl exit code: $CURL_RC"
echo

echo "=== OUTPUT CHECK ==="
if [[ -f "$OUTFILE" ]]; then
  ls -lh "$OUTFILE"
  echo "First 40 lines:"
  head -n 40 "$OUTFILE"
else
  echo "ERROR: Output file not created"
fi

echo
echo "End time: $(date)"
echo "=========== JOB END ==========="
