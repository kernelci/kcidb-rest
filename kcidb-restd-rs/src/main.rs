/*
KCIDB-Rust REST submissions receiver

1)Verify user authentication
2)Create file name with suffix _temp, until it is ready to be
   processed
3)After all file received, rename the file to the final name
4)Validate if the submission is valid JSON
* Optionally validate some other things

*/

use axum::routing::post;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::extract::State;
use axum::http::header::HeaderMap;
use clap::Parser;
use std::path::Path;
use std::sync::Arc;
use serde::{Serialize, Deserialize};
use rand::Rng;
use jsonwebtoken::{decode, Validation, DecodingKey};
use tokio::net::TcpListener;
use axum::Router;
use tower_http::limit::RequestBodyLimitLayer;


#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    /// The port to listen on
    #[clap(short, long, default_value = "3000")]
    port: u16,
    /// The host to listen on
    #[clap(short = 'b', long, default_value = "0.0.0.0")]
    host: String,
    /// The path to the directory to store the received files
    #[clap(short = 'd', long, default_value = "/app/spool")]
    directory: String,
    /// JWT secret
    #[clap(short, long, default_value = "secret")]
    jwt_secret: String,
}

struct AppState {    
    directory: String,
    jwt_secret: String,
}

fn verify_submission_path(path: &str) -> bool {
    let path = Path::new(path);
    path.exists() && path.is_dir()
}

#[tokio::main]
async fn main() {
    let limit_layer = RequestBodyLimitLayer::new(512 * 1024 * 1024);
    let args = Args::parse();
    let app_state = Arc::new(AppState {
        directory: args.directory,
        jwt_secret: args.jwt_secret,
    });
    if !verify_submission_path(&app_state.directory) {
        eprintln!("Error: submissions path {} does not exist or is not a directory", app_state.directory);
        std::process::exit(1);
    }
    // if default value - warn
    if app_state.jwt_secret == "secret" {
        eprintln!("Warning: JWT secret is default value");
    }
    // if secret is empty, warn
    if app_state.jwt_secret.is_empty() {
        eprintln!("Warning: JWT secret is empty, disabling authentication");
    }
    println!("Listening on {}:{}, submissions path: {}", args.host, args.port, app_state.directory);
    // change body limit to 512MB
    let app = Router::new()
        .route("/submit", post(receive_submission))
        .with_state(app_state)
        .layer(limit_layer)
        .layer(axum::extract::DefaultBodyLimit::max(512 * 1024 * 1024));
    let tcp_listener = TcpListener::bind((args.host, args.port)).await.unwrap();
    axum::serve(tcp_listener, app).await.unwrap();
}

fn verify_auth(headers: HeaderMap, state: Arc<AppState>) -> Result<(), String> {
    // if secret is empty, return Ok
    if state.jwt_secret.is_empty() {
        return Ok(());
    }
    let jwt_r = headers.get("Authorization");
    let jwt = match jwt_r {
        Some(jwt) => jwt,
        None => return Err("JWT is required".to_string()),
    };
    let jwt_str_r = jwt.to_str();
    let jwt_str = match jwt_str_r {
        Ok(jwt_str) => jwt_str,
        Err(_) => return Err("Missing or invalid JWT".to_string()),
    };
    let jwt_str = jwt_str.split(" ").nth(1).unwrap();
    let jwt = verify_jwt(jwt_str, &state.jwt_secret);
    match jwt {
        Ok(jwt) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

// Answer STATUS 200 if the submission is valid
async fn receive_submission(
    headers: HeaderMap,
    State(state): State<Arc<AppState>>,
    body: String,
) -> impl IntoResponse {
    let auth_result = verify_auth(headers, state.clone());
    match auth_result {
        Ok(()) => (),
        Err(e) => return (StatusCode::UNAUTHORIZED, e.to_string()),
    }

    let submission_json = serde_json::from_str::<serde_json::Value>(&body);
    match submission_json {
        Ok(submission) => {
            let size = body.len();
            println!("Received submission size: {}", size);
            let submission_id = random_string(32);
            let submission_file = format!("{}/submission-{}.json.temp", state.directory, submission_id);
            std::fs::write(&submission_file, &body).unwrap();
            // on completion, rename to submission.json
            std::fs::rename(&submission_file, &format!("{}/submission-{}.json", state.directory, submission_id)).unwrap();
            println!("Submission {} received", submission_id);
            (StatusCode::OK, "Submission received".to_string())
        }
        Err(e) => {
            println!("Error: {}", e);
            (StatusCode::BAD_REQUEST, "Invalid submission format".to_string())
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
struct JWT {
    origin: String,
    gendate: String,
}

fn verify_jwt(token: &str, secret: &str) -> Result<JWT, jsonwebtoken::errors::Error> {
    let key = DecodingKey::from_secret(secret.as_bytes());
    let token = decode::<JWT>(token, &key, &Validation::default())?;
    Ok(token.claims)
}

/* STUB for now */
/*
fn generate_jwt(origin: &str, gendate: &str, secret: &str) -> Result<String, jsonwebtoken::errors::Error> {
    let key = EncodingKey::from_secret(secret.as_bytes());
    let token = encode(&Header::default(), &JWT { origin: origin.to_string(), gendate: gendate.to_string() }, &key)?;
    Ok(token)
}
*/


// TODO: Fix this
fn random_string(length: usize) -> String {
    let mut rng = rand::rng();
    // rng.sample(rand::distr::Alphanumeric) as char
    let mut s = String::new();
    for _ in 0..length {
        s.push(rng.sample(rand::distr::Alphanumeric) as char);
    }
    s
}
