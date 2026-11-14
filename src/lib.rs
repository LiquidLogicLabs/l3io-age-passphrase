#![deny(unsafe_code)]

use std::io::{Read, Write};
use std::iter;

use age::armor::{ArmoredReader, ArmoredWriter, Format};
use age::scrypt;
use age::{Decryptor, Encryptor};
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use pyo3_file::PyFileLikeObject;

create_exception!(l3io_age_passphrase, EncryptError, PyException);
create_exception!(l3io_age_passphrase, DecryptError, PyException);

/// The scrypt work factor every file is encrypted with (`N = 2^18`), stock `age -p`'s.
///
/// age's `Encryptor::with_user_passphrase` and `scrypt::Identity::new` instead time
/// a small scrypt run on the wall clock: the encryption work factor and the largest
/// one decryption accepts (that target + 4) then depend on how busy the host is,
/// so a file encrypted while the host was idle is refused ("Excessive work
/// parameter") while it is busy, and one encrypted while it is busy is weak.
const WORK_FACTOR: u8 = 18;

/// The largest scrypt work factor decryption accepts (`N = 2^22`, 4 GiB), fixed
/// for the reason above. A file asking for more is refused before any work.
const MAX_WORK_FACTOR: u8 = 22;

fn encryptor(passphrase: &str) -> Encryptor {
    let mut recipient = scrypt::Recipient::new(passphrase.into());
    recipient.set_work_factor(WORK_FACTOR);
    Encryptor::with_recipients(iter::once(&recipient as _))
        .expect("a sole scrypt recipient is always a valid recipient set")
}

fn identity(passphrase: &str) -> scrypt::Identity {
    let mut identity = scrypt::Identity::new(passphrase.into());
    identity.set_max_work_factor(MAX_WORK_FACTOR);
    identity
}

fn from_pyobject(file: Py<PyAny>, read_only: bool) -> PyResult<PyFileLikeObject> {
    PyFileLikeObject::with_requirements(file, read_only, !read_only, false, false)
}

#[pyfunction]
#[pyo3(signature = (plaintext, passphrase, armored=false))]
fn encrypt<'py>(
    py: Python<'py>,
    plaintext: &[u8],
    passphrase: &str,
    armored: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    let encryptor = encryptor(passphrase);
    let mut encrypted = vec![];
    let format = if armored {
        Format::AsciiArmor
    } else {
        Format::Binary
    };
    let mut writer = encryptor
        .wrap_output(ArmoredWriter::wrap_output(&mut encrypted, format)?)
        .map_err(|e| EncryptError::new_err(e.to_string()))?;
    writer
        .write_all(plaintext)
        .map_err(|e| EncryptError::new_err(e.to_string()))?;
    writer
        .finish()
        .map_err(|e| EncryptError::new_err(e.to_string()))?
        .finish()
        .map_err(|e| EncryptError::new_err(e.to_string()))?;
    Ok(PyBytes::new(py, &encrypted))
}

#[pyfunction]
fn decrypt<'py>(
    py: Python<'py>,
    ciphertext: &[u8],
    passphrase: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    let decryptor = Decryptor::new_buffered(ArmoredReader::new(ciphertext))
        .map_err(|e| DecryptError::new_err(e.to_string()))?;
    let mut decrypted = vec![];
    let mut reader = decryptor
        .decrypt(iter::once(&identity(passphrase) as _))
        .map_err(|e| DecryptError::new_err(e.to_string()))?;
    reader
        .read_to_end(&mut decrypted)
        .map_err(|e| DecryptError::new_err(e.to_string()))?;
    Ok(PyBytes::new(py, &decrypted))
}

#[pyfunction]
#[pyo3(signature = (reader, writer, passphrase, armored=false))]
fn encrypt_io(
    reader: Py<PyAny>,
    writer: Py<PyAny>,
    passphrase: &str,
    armored: bool,
) -> PyResult<()> {
    let reader = from_pyobject(reader, true)?;
    let writer = from_pyobject(writer, false)?;
    let mut reader = std::io::BufReader::new(reader);
    let mut writer = std::io::BufWriter::new(writer);

    let encryptor = encryptor(passphrase);
    let format = if armored {
        Format::AsciiArmor
    } else {
        Format::Binary
    };
    let mut writer = encryptor
        .wrap_output(ArmoredWriter::wrap_output(&mut writer, format)?)
        .map_err(|e| EncryptError::new_err(e.to_string()))?;

    std::io::copy(&mut reader, &mut writer).map_err(|e| EncryptError::new_err(e.to_string()))?;

    writer
        .finish()
        .map_err(|e| EncryptError::new_err(e.to_string()))?
        .finish()
        .map_err(|e| EncryptError::new_err(e.to_string()))?;
    Ok(())
}

#[pyfunction]
fn decrypt_io(reader: Py<PyAny>, writer: Py<PyAny>, passphrase: &str) -> PyResult<()> {
    let reader = from_pyobject(reader, true)?;
    let writer = from_pyobject(writer, false)?;
    let reader = std::io::BufReader::new(reader);
    let mut writer = std::io::BufWriter::new(writer);

    let decryptor = Decryptor::new_buffered(ArmoredReader::new(reader))
        .map_err(|e| DecryptError::new_err(e.to_string()))?;
    let mut reader = decryptor
        .decrypt(iter::once(&identity(passphrase) as _))
        .map_err(|e| DecryptError::new_err(e.to_string()))?;

    std::io::copy(&mut reader, &mut writer).map_err(|e| DecryptError::new_err(e.to_string()))?;
    Ok(())
}

#[pymodule]
fn l3io_age_passphrase(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("EncryptError", py.get_type::<EncryptError>())?;
    m.add("DecryptError", py.get_type::<DecryptError>())?;
    m.add_wrapped(wrap_pyfunction!(encrypt))?;
    m.add_wrapped(wrap_pyfunction!(decrypt))?;
    m.add_wrapped(wrap_pyfunction!(encrypt_io))?;
    m.add_wrapped(wrap_pyfunction!(decrypt_io))?;
    Ok(())
}
