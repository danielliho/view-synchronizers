#!/bin/bash
#SBATCH --job-name=oneshot-das5
#SBATCH --output=slurm-%j.out.ansi
#SBATCH --error=slurm-%j.err.ansi
#SBATCH --time=01:15:00
#SBATCH -N 32
#SBATCH --ntasks-per-node=1

set -eo pipefail

# DAS-5 jobs do not run login shell setup, so initialize the module shell
# environment explicitly. The DAS-5 docs recommend this for batch jobs.
. /etc/bashrc
if [ -f /etc/profile.d/lmod.sh ]; then
    . /etc/profile.d/lmod.sh
fi

set -u

module load prun || true

# DAS-5 home directories are mounted on compute nodes. Run from the shared
# checkout so experiments.py, binaries, config, and stats are all in one place.
PROJECT_DIR="${DAMYSUS_PROJECT_DIR:-/home/dlihotsk/view-synchronizers}"
cd "${PROJECT_DIR}"
export MPLBACKEND=Agg

prepend_path() {
    var_name="$1"
    value="$2"
    if [ -d "${value}" ]; then
        current_value="${!var_name:-}"
        if [ -n "${current_value}" ]; then
            export "${var_name}=${value}:${current_value}"
        else
            export "${var_name}=${value}"
        fi
    fi
}

find_dir_with_file() {
    rel_file="$1"
    shift
    for prefix in "$@"; do
        if [ -n "${prefix}" ] && [ -f "${prefix}/${rel_file}" ]; then
            printf '%s\n' "${prefix}"
            return 0
        fi
    done
    return 1
}

HOME_PREFIXES="${DAMYSUS_DEPS_PREFIXES:-${HOME}/.local:${HOME}/opt:${HOME}/openssl:${HOME}/opt/openssl:${HOME}/libuv:${HOME}/opt/libuv:/usr:/usr/local:/opt}"
OLD_IFS="${IFS}"
IFS=":"
for prefix in ${HOME_PREFIXES}; do
    prepend_path CPATH "${prefix}/include"
    prepend_path C_INCLUDE_PATH "${prefix}/include"
    prepend_path CPLUS_INCLUDE_PATH "${prefix}/include"
    prepend_path LIBRARY_PATH "${prefix}/lib64"
    prepend_path LIBRARY_PATH "${prefix}/lib"
    prepend_path LD_LIBRARY_PATH "${prefix}/lib64"
    prepend_path LD_LIBRARY_PATH "${prefix}/lib"
    prepend_path PKG_CONFIG_PATH "${prefix}/lib64/pkgconfig"
    prepend_path PKG_CONFIG_PATH "${prefix}/lib/pkgconfig"
    prepend_path PKG_CONFIG_PATH "${prefix}/share/pkgconfig"
done
IFS="${OLD_IFS}"

OPENSSL_INCLUDE="$(find "${HOME}" -path '*/include/openssl/sha.h' -print -quit 2>/dev/null || true)"
if [ -n "${OPENSSL_INCLUDE}" ]; then
    OPENSSL_PREFIX="${OPENSSL_INCLUDE%/include/openssl/sha.h}"
    prepend_path CPATH "${OPENSSL_PREFIX}/include"
    prepend_path C_INCLUDE_PATH "${OPENSSL_PREFIX}/include"
    prepend_path CPLUS_INCLUDE_PATH "${OPENSSL_PREFIX}/include"
    prepend_path LIBRARY_PATH "${OPENSSL_PREFIX}/lib64"
    prepend_path LIBRARY_PATH "${OPENSSL_PREFIX}/lib"
    prepend_path LD_LIBRARY_PATH "${OPENSSL_PREFIX}/lib64"
    prepend_path LD_LIBRARY_PATH "${OPENSSL_PREFIX}/lib"
    prepend_path PKG_CONFIG_PATH "${OPENSSL_PREFIX}/lib64/pkgconfig"
    prepend_path PKG_CONFIG_PATH "${OPENSSL_PREFIX}/lib/pkgconfig"
fi

LIBUV_PREFIX="${DAMYSUS_LIBUV_PREFIX:-}"
if [ -z "${LIBUV_PREFIX}" ] && [ -f /usr/include/uv.h ]; then
    LIBUV_PREFIX="/usr"
fi
if [ -n "${LIBUV_PREFIX}" ]; then
    prepend_path PKG_CONFIG_PATH "${LIBUV_PREFIX}/lib64/pkgconfig"
    prepend_path PKG_CONFIG_PATH "${LIBUV_PREFIX}/lib/pkgconfig"
    prepend_path CPATH "${LIBUV_PREFIX}/include"
    prepend_path C_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path CPLUS_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path LIBRARY_PATH "${LIBUV_PREFIX}/lib64"
    prepend_path LIBRARY_PATH "${LIBUV_PREFIX}/lib"
    prepend_path LD_LIBRARY_PATH "${LIBUV_PREFIX}/lib64"
    prepend_path LD_LIBRARY_PATH "${LIBUV_PREFIX}/lib"
fi

LIBUV_PC=""
if [ -z "${LIBUV_PREFIX}" ]; then
    LIBUV_PC="$(find "${HOME}" /usr /usr/local -path '*/pkgconfig/libuv.pc' -print -quit 2>/dev/null || true)"
fi
if [ -n "${LIBUV_PC}" ]; then
    LIBUV_PKGCONFIG_DIR="${LIBUV_PC%/libuv.pc}"
    LIBUV_LIB_DIR="${LIBUV_PKGCONFIG_DIR%/pkgconfig}"
    LIBUV_PREFIX="${LIBUV_LIB_DIR%/lib}"
    LIBUV_PREFIX="${LIBUV_PREFIX%/lib64}"
    prepend_path PKG_CONFIG_PATH "${LIBUV_PKGCONFIG_DIR}"
    prepend_path CPATH "${LIBUV_PREFIX}/include"
    prepend_path C_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path CPLUS_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path LIBRARY_PATH "${LIBUV_LIB_DIR}"
    prepend_path LD_LIBRARY_PATH "${LIBUV_LIB_DIR}"
fi

if [ -n "${LIBUV_PREFIX}" ] && [ -f "${LIBUV_PREFIX}/include/uv.h" ]; then
    LIBUV_INCLUDE="${LIBUV_PREFIX}/include/uv.h"
else
    LIBUV_INCLUDE="$(find "${HOME}" /usr /usr/local -path '*/include/uv.h' -print -quit 2>/dev/null || true)"
fi
if [ -n "${LIBUV_INCLUDE}" ]; then
    LIBUV_PREFIX="${LIBUV_INCLUDE%/include/uv.h}"
    prepend_path CPATH "${LIBUV_PREFIX}/include"
    prepend_path C_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path CPLUS_INCLUDE_PATH "${LIBUV_PREFIX}/include"
    prepend_path LIBRARY_PATH "${LIBUV_PREFIX}/lib64"
    prepend_path LIBRARY_PATH "${LIBUV_PREFIX}/lib"
    prepend_path LD_LIBRARY_PATH "${LIBUV_PREFIX}/lib64"
    prepend_path LD_LIBRARY_PATH "${LIBUV_PREFIX}/lib"
    prepend_path PKG_CONFIG_PATH "${LIBUV_PREFIX}/lib64/pkgconfig"
    prepend_path PKG_CONFIG_PATH "${LIBUV_PREFIX}/lib/pkgconfig"
fi

EXTRA_CFLAGS="${EXTRA_CFLAGS:-}"
EXTRA_LDLIBS="${EXTRA_LDLIBS:-}"
if [ -n "${OPENSSL_INCLUDE}" ]; then
    EXTRA_CFLAGS="${EXTRA_CFLAGS} -I${OPENSSL_PREFIX}/include"
    if [ -d "${OPENSSL_PREFIX}/lib64" ]; then
        EXTRA_LDLIBS="${EXTRA_LDLIBS} -L${OPENSSL_PREFIX}/lib64"
    elif [ -d "${OPENSSL_PREFIX}/lib" ]; then
        EXTRA_LDLIBS="${EXTRA_LDLIBS} -L${OPENSSL_PREFIX}/lib"
    fi
fi
if [ -n "${LIBUV_INCLUDE}" ]; then
    EXTRA_CFLAGS="${EXTRA_CFLAGS} -I${LIBUV_PREFIX}/include"
    if [ -d "${LIBUV_PREFIX}/lib64" ]; then
        EXTRA_LDLIBS="${EXTRA_LDLIBS} -L${LIBUV_PREFIX}/lib64"
    elif [ -d "${LIBUV_PREFIX}/lib" ]; then
        EXTRA_LDLIBS="${EXTRA_LDLIBS} -L${LIBUV_PREFIX}/lib"
    fi
fi
export EXTRA_CFLAGS
export EXTRA_LDLIBS

if [ -z "${LIBUV_INCLUDE}" ] && ! "${PKG_CONFIG:-pkg-config}" --exists libuv; then
    echo "WARNING: libuv headers not found on this compute node." >&2
    echo "The job will run with --nocompil; build on fs0/login first, where /usr/include/uv.h exists." >&2
    FORCE_NOCOMPIL=1
else
    FORCE_NOCOMPIL="${FORCE_NOCOMPIL:-0}"
fi

SGX_SDK="${DAMYSUS_SGX_SDK:-${SGX_SDK:-}}"
if [ -z "${SGX_SDK}" ]; then
    SGX_SDK="$(find_dir_with_file environment \
        "${HOME}/opt/intel/sgxsdk" \
        "${HOME}/sgxsdk" \
        "${HOME}/intel/sgxsdk" \
        "${HOME}/linux-sgx/linux/installer/bin/sgxsdk" \
        "${HOME}/linux-sgx/sgxsdk" || true)"
fi
if [ -z "${SGX_SDK}" ] || [ ! -f "${SGX_SDK}/environment" ]; then
    echo "ERROR: SGX SDK environment file was not found." >&2
    echo "Set DAMYSUS_SGX_SDK to the directory that contains the SGX SDK environment file." >&2
    exit 1
fi
export SGX_SDK
. "${SGX_SDK}/environment"

SGXSSL_ROOT="${DAMYSUS_SGXSSL_ROOT:-${SGXSSL_ROOT:-}}"
if [ -z "${SGXSSL_ROOT}" ]; then
    SGXSSL_ROOT="$(find_dir_with_file include/sgx_tsgxssl.edl \
        "${HOME}/opt/intel/sgxssl" \
        "${HOME}/sgxssl" \
        "${HOME}/intel/sgxssl" \
        "/opt/intel/sgxssl" || true)"
fi
if [ -n "${SGXSSL_ROOT}" ]; then
    export SGXSSL_ROOT
    export SGXSSL_INCLUDE_PATH="${SGXSSL_ROOT}/include"
    export SGXSSL_UNTRUSTED_LIB_PATH="${SGXSSL_ROOT}/lib64"
    export SGXSSL_TRUSTED_LIB_PATH="${SGXSSL_ROOT}/lib64"
    prepend_path LD_LIBRARY_PATH "${SGXSSL_ROOT}/lib64"
    prepend_path LIBRARY_PATH "${SGXSSL_ROOT}/lib64"
fi

LIBSTDCXX_SO="${DAMYSUS_LIBSTDCXX_SO:-}"
if [ -z "${LIBSTDCXX_SO}" ]; then
    LIBSTDCXX_SO="$(find "${HOME}" /opt/rh /opt/ohpc/pub/compiler -path '*/libstdc++.so.6' -print -quit 2>/dev/null || true)"
fi
if [ -n "${LIBSTDCXX_SO}" ]; then
    LIBSTDCXX_DIR="${LIBSTDCXX_SO%/libstdc++.so.6}"
    prepend_path LD_LIBRARY_PATH "${LIBSTDCXX_DIR}"
    echo "libstdc++ runtime: ${LIBSTDCXX_SO}"
else
    echo "WARNING: no alternate libstdc++.so.6 found; compute nodes may use an older system libstdc++." >&2
fi

echo "SGX_SDK: ${SGX_SDK}"
echo "SGXSSL_ROOT: ${SGXSSL_ROOT:-not set}"
echo "OpenSSL include: ${OPENSSL_INCLUDE:-not found}"
echo "libuv include: ${LIBUV_INCLUDE:-not found}"
echo "EXTRA_CFLAGS: ${EXTRA_CFLAGS:-}"
echo "EXTRA_LDLIBS: ${EXTRA_LDLIBS:-}"
echo "PKG_CONFIG_PATH: ${PKG_CONFIG_PATH:-}"
if ! "${PKG_CONFIG:-pkg-config}" --exists openssl libuv; then
    echo "WARNING: pkg-config cannot find openssl and/or libuv; falling back to CPATH/LIBRARY_PATH and -lcrypto -lssl -luv" >&2
fi

VENV_DIR="${DAMYSUS_VENV_DIR:-${PROJECT_DIR}/.venv}"
if [ -f "${VENV_DIR}/bin/activate" ]; then
    . "${VENV_DIR}/bin/activate"
else
    echo "ERROR: Python venv not found at ${VENV_DIR}" >&2
    echo "Set DAMYSUS_VENV_DIR or create the venv with matplotlib installed." >&2
    exit 1
fi

PYTHON="${DAMYSUS_PYTHON:-${VENV_DIR}/bin/python3}"
if [ ! -x "${PYTHON}" ]; then
    PYTHON="${VENV_DIR}/bin/python"
fi
if [ ! -x "${PYTHON}" ]; then
    echo "ERROR: Python executable not found in ${VENV_DIR}/bin" >&2
    exit 1
fi

if ! "${PYTHON}" -c "import matplotlib" >/dev/null 2>&1; then
    echo "matplotlib is missing from ${VENV_DIR}; installing it now"
    "${PYTHON}" -m pip install --upgrade pip
    "${PYTHON}" -m pip install matplotlib
fi

"${PYTHON}" -c "import sys, matplotlib; print('matplotlib', matplotlib.__version__, 'from', sys.executable)"

echo "SLURM job: ${SLURM_JOB_ID}"
echo "Project dir: ${PROJECT_DIR}"
echo "Python: ${PYTHON}"
echo "Allocated nodes:"
scontrol show hostnames "${SLURM_JOB_NODELIST}"

echo "Starting Lewis-Pye"
start_time=$(date +%s)
echo "Start time: $(date)"

if [ "$#" -gt 0 ]; then
    if [ "${FORCE_NOCOMPIL:-0}" = "1" ]; then
        "${PYTHON}" experiments.py --das5 --nodisplay --nocompil "$@"
    else
        "${PYTHON}" experiments.py --das5 --nodisplay "$@"
    fi
else
    if [ "${FORCE_NOCOMPIL:-0}" = "1" ]; then
        "${PYTHON}" experiments.py --das5 --nodisplay --nocompil --p8 --faults 2 --repeats 1
    else
        "${PYTHON}" experiments.py --das5 --nodisplay --p8 --faults 2 --repeats 1
    fi
fi

end_time=$(date +%s)
echo "End time: $(date)"
duration=$((end_time - start_time))
echo "Total duration: ${duration} seconds ($((duration / 60)) minutes $((duration % 60)) seconds)"

