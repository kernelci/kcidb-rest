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
// headermap
use axum::http::header::HeaderMap;
use clap::Parser;
use std::path::Path;
use std::sync::Arc;
// jwt
use serde::{Serialize, Deserialize};
use jsonwebtoken::{decode, Validation, DecodingKey};
use tokio::net::TcpListener;
use axum::Router;

#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    /// The port to listen on
    #[clap(short, long, default_value = "3000")]
    port: u16,
    /// The host to listen on
    #[clap(short, long, default_value = "0.0.0.0")]
    host: String,
    /// The path to the directory to store the received files
    #[clap(short, long, default_value = "/var/www/kcidb-rest/submissions")]
    path: String,
    /// JWT secret
    #[clap(short, long, default_value = "secret")]
    jwt_secret: String,
}

struct AppState {    
    path: String,
    jwt_secret: String,
}

fn verify_submission_path(path: &str) -> bool {
    let path = Path::new(path);
    path.exists() && path.is_dir()
}

#[tokio::main]
async fn main() {
    let args = Args::parse();
    let app_state = Arc::new(AppState {
        path: args.path,
        jwt_secret: args.jwt_secret,
    });
    if !verify_submission_path(&app_state.path) {
        eprintln!("Error: submissions path {} does not exist or is not a directory", app_state.path);
        std::process::exit(1);
    }
    // if default value - warn
    if app_state.jwt_secret == "secret" {
        eprintln!("Warning: JWT secret is default value");
    }
    println!("Listening on {}:{}, submissions path: {}", args.host, args.port, app_state.path);
    // change body limit to 512MB
    let app = Router::new()
        .route("/submit", post(receive_submission))
        .with_state(app_state)
        .with_state(axum::extract::DefaultBodyLimit::max(512 * 1024 * 1024));
    let tcp_listener = TcpListener::bind((args.host, args.port)).await.unwrap();
    axum::serve(tcp_listener, app).await.unwrap();
}

// Answer STATUS 200 if the submission is valid
async fn receive_submission(
    headers: HeaderMap,
    State(state): State<Arc<AppState>>,
    body: String,
) -> impl IntoResponse {

    let jwt_r = headers.get("Authorization");
    let jwt = match jwt_r {
        Some(jwt) => jwt,
        None => return (StatusCode::BAD_REQUEST, "JWT is required"),
    };
    let jwt_str = jwt.to_str().unwrap();
    let jwt_str = jwt_str.split(" ").nth(1).unwrap();
    let jwt = verify_jwt(jwt_str, &state.jwt_secret);
    match jwt {
        Ok(jwt) => {
            println!("JWT is valid: {:?}", jwt);
        }
        Err(e) => {
            println!("Error: {}", e);
            return (StatusCode::BAD_REQUEST, "Invalid JWT");
        }
    }

    let submission_json = serde_json::from_str::<Submission>(&body);
    match submission_json {
        Ok(submission) => {
            println!("Received submission: {:?}", submission);
            (StatusCode::OK, "Submission received")
        }
        Err(e) => {
            println!("Error: {}", e);
            (StatusCode::BAD_REQUEST, "Invalid submission format")
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
struct Submission {
    submission: String,
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