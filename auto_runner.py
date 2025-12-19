import os
import json
import random
import subprocess
import shutil
import argparse
import sys
from pom_modifier import inject_jacoco_into_pom

# ==================== Global Variables (initialized by command line arguments) ====================
CONTAINER_NAME = "" 
PARSER_JAR_NAME = ""
OUTPUT_DIR = ""
SAMPLE_RATIO = 3.0
REMOTE_WORKDIR = "/app"
MVN_EXECUTABLE = "mvn"
# =================================================================

def run_cmd(cmd, silent=False):
    if not silent: print(f"👉 {cmd}")
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='ignore')

def extract_class_name(file_path):
    """Extract fully qualified class name from filePath (helper function)"""
    try:
        if "src/test/java/" in file_path:
            part = file_path.split("src/test/java/")[1]
        elif "src/main/java/" in file_path:
            part = file_path.split("src/main/java/")[1]
        else:
            return os.path.basename(file_path).replace(".java", "")
        return part.replace(".java", "").replace("/", ".")
    except:
        return os.path.basename(file_path).replace(".java", "")

def force_cleanup(path):
    """Force cleanup a directory, using Docker if local permission denied"""
    if not os.path.exists(path): return
    try:
        shutil.rmtree(path)
    except Exception as e:
        print(f"   ⚠️ Local cleanup failed, trying via Docker...")
        cwd = os.getcwd()
        # Mount current dir to /work and delete the target folder
        # Note: path should be relative to cwd for this to work simply
        target = os.path.relpath(path, cwd)
        cmd = f"docker run --rm -v \"{cwd}\":/work alpine rm -rf /work/{target}"
        run_cmd(cmd, silent=True)

def step0_check_tests_existence():
    """Step 0: Check if tests exist in the container"""
    print(f"\n🔍 Step 0: Checking for tests in {CONTAINER_NAME}...")
    
    # Count Test files
    cmd = f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} find . -name '*Test.java' | wc -l"
    res_count = run_cmd(cmd, silent=True)
    count = int(res_count.stdout.strip()) if res_count.stdout.strip().isdigit() else 0
    
    print(f"   ℹ️ Found approximately {count} Test.java files.")
    
    if count == 0:
        print("   ❌ No *Test.java files found in the container. Please check the working directory or project structure.")
        sys.exit(1)
    else:
        print("   ✅ Tests detected.")

def step1_prepare_environment():
    """Step 1: Put Parser into container and modify POM"""
    global MVN_EXECUTABLE
    print(f"\n📦 Step 1: Preparing Environment for [{CONTAINER_NAME}]...")
    
    # Check for mvnw
    res = run_cmd(f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} test -f mvnw")
    if res.returncode == 0:
        print("   ✅ Maven Wrapper (mvnw) detected. Using ./mvnw")
        MVN_EXECUTABLE = "./mvnw"
    else:
        print("   ℹ️ Maven Wrapper not found. Using system mvn")
        MVN_EXECUTABLE = "mvn"
    
    # 1.1 Upload Parser JAR to container root directory (/app)
    print(f"   Uploading {PARSER_JAR_NAME}...")
    if not os.path.exists(PARSER_JAR_NAME):
        print(f"❌ Error: Jar file '{PARSER_JAR_NAME}' not found locally!")
        sys.exit(1)

    run_cmd(f"docker cp {PARSER_JAR_NAME} {CONTAINER_NAME}:{REMOTE_WORKDIR}/parser.jar")

    # 1.2 Inject JaCoCo into pom.xml
    print("   Injecting JaCoCo into pom.xml...")
    # First clean up any local remaining temp files
    if os.path.exists("./temp_pom.xml"): os.remove("./temp_pom.xml")
    
    res = run_cmd(f"docker cp {CONTAINER_NAME}:{REMOTE_WORKDIR}/pom.xml ./temp_pom.xml")
    if res.returncode != 0:
        print(f"❌ Failed to copy pom.xml from container. Is container '{CONTAINER_NAME}' running?")
        sys.exit(1)
    
    try:
        inject_jacoco_into_pom("./temp_pom.xml") # Call pom_modifier.py
        run_cmd(f"docker cp ./temp_pom.xml {CONTAINER_NAME}:{REMOTE_WORKDIR}/pom.xml")
        print("   ✅ JaCoCo injected.")
    except Exception as e:
        print(f"❌ POM modification failed: {e}")
        sys.exit(1)
    finally:
        if os.path.exists("./temp_pom.xml"): os.remove("./temp_pom.xml")

def step2_run_parser_and_get_tests():
    """Step 2: Run Parser locally (to avoid Java version mismatch in container)"""
    print("\n🧠 Step 2: Running Parser locally...")
    
    # 2.1 Copy project from container to local temp
    # Use a unique temp dir to avoid conflicts with previous failed runs
    import time
    local_project_path = f"./temp_project_source_{int(time.time())}"
    # local_project_path = "./temp_project_source"
    # force_cleanup(local_project_path)
    os.makedirs(local_project_path, exist_ok=True)
    
    print(f"   Copying project from {CONTAINER_NAME}:{REMOTE_WORKDIR} to {local_project_path} (using tar to exclude target)...")
    
    # Use tar inside container to package source code, excluding target directories
    # This avoids permission issues and speeds up transfer
    tar_remote_path = f"{REMOTE_WORKDIR}/project_source.tar"
    tar_local_path = f"./temp_project_source_{int(time.time())}.tar"
    
    # Create tarball inside container
    # Exclude target, .git, and hidden files to keep it clean
    # Note: --exclude pattern matches the file name component
    tar_cmd = f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} tar -cf project_source.tar --exclude='target' --exclude='.git' ."
    res = run_cmd(tar_cmd)
    if res.returncode != 0:
        print(f"❌ Failed to create tarball in container: {res.stderr}")
        return [], []
        
    # Copy tarball to local
    run_cmd(f"docker cp {CONTAINER_NAME}:{tar_remote_path} {tar_local_path}")
    
    # Remove tarball from container to save space
    run_cmd(f"docker exec {CONTAINER_NAME} rm {tar_remote_path}", silent=True)
    
    # Extract tarball locally
    if os.path.exists(tar_local_path):
        run_cmd(f"tar -xf {tar_local_path} -C {local_project_path}")
        os.remove(tar_local_path)
    else:
        print("❌ Failed to retrieve tarball.")
        return [], []

    # Debug: Check if pom.xml exists
    if not os.path.exists(os.path.join(local_project_path, "pom.xml")):
        print(f"⚠️ Warning: pom.xml not found in {local_project_path}")
        run_cmd(f"ls -F {local_project_path}")
    
    # 2.2 Execute Parser locally
    cmd = f"java -jar {PARSER_JAR_NAME} {local_project_path} ./temp_tests.json"
    
    res = run_cmd(cmd)
    if res.returncode != 0:
        print(f"❌ Parser Execution Failed:\n{res.stderr}")
        force_cleanup(local_project_path)
        return [], []
        
    # 2.3 Parse JSON
    if not os.path.exists("./temp_tests.json"):
        print("❌ Failed to generate JSON.")
        print(f"STDOUT: {res.stdout}")
        print(f"STDERR: {res.stderr}")
        force_cleanup(local_project_path)
        return [], []

    with open("./temp_tests.json", 'r') as f:
        data = json.load(f)
    
    os.remove("./temp_tests.json")
    force_cleanup(local_project_path)
    
    pts = []
    nonpts = []
    
    for item in data:
        file_path = item.get("filePath", "")
        method_name = item.get("methodName", "")
        annotations = item.get("annotations", [])
        
        class_name = extract_class_name(file_path)
        test_id = f"{class_name}#{method_name}"
        
        if "ParameterizedTest" in annotations:
            pts.append(test_id)
        else:
            nonpts.append(test_id)
            
    return list(set(pts)), list(set(nonpts))

def step3_run_tests_loop(test_list, category):
    """Step 3: Loop through tests and save XML"""
    print(f"\n🚀 Step 3: Running {len(test_list)} {category} tests...")
    
    # Create a subdirectory for current project to prevent different projects from mixing
    # e.g. ./experiment_data/sag-commons-math/pt/
    # This way when you run multiple projects, data is isolated
    project_output_dir = os.path.join(OUTPUT_DIR, CONTAINER_NAME, category)
    
    for i, test_id in enumerate(test_list):
        safe_name = test_id.replace("#", "_").replace(".", "_")
        local_xml = os.path.join(project_output_dir, f"{safe_name}.xml")
        
        if os.path.exists(local_xml):
            print(f"   [{i+1}/{len(test_list)}] Skipping {test_id} (Done)")
            continue

        print(f"   [{i+1}/{len(test_list)}] Running: {test_id}")
        
        # Clean up any existing jacoco.xml files in any module
        run_cmd(f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} find . -name jacoco.xml -delete", silent=True)
        
        mvn_cmd = f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} {MVN_EXECUTABLE} test -Dtest={test_id} -DfailIfNoTests=false -Drat.skip=true"
        res = run_cmd(mvn_cmd, silent=True)

        if res.returncode != 0:
            print(f"   ❌ Build/Test Failed for {test_id}. See build_failures.log")
            with open("build_failures.log", "a") as log_file:
                log_file.write(f"=== {test_id} ===\n")
                log_file.write(res.stdout)
                log_file.write(res.stderr)
                log_file.write("\n==================\n")
        
        # Find the generated jacoco.xml (it should be in one of the modules)
        find_res = run_cmd(f"docker exec -w {REMOTE_WORKDIR} {CONTAINER_NAME} find . -name jacoco.xml | head -n 1", silent=True)
        remote_path = find_res.stdout.strip()
        
        if remote_path:
            if remote_path.startswith("./"): remote_path = remote_path[2:]
            os.makedirs(os.path.dirname(local_xml), exist_ok=True)
            run_cmd(f"docker cp {CONTAINER_NAME}:{REMOTE_WORKDIR}/{remote_path} {local_xml}", silent=True)
        else:
            print(f"   ⚠️ No XML for {test_id}")

if __name__ == "__main__":
    # === Parameter parsing ===
    parser = argparse.ArgumentParser(description="Auto Runner for PT Empirical Study")
    
    # Required parameter: container name
    parser.add_argument("container_name", help="The Docker container name (e.g., sag-commons-math)")
    
    # Optional parameters
    parser.add_argument("--jar", default="test-parser-1.0-SNAPSHOT-jar-with-dependencies.jar", help="Path to parser JAR")
    parser.add_argument("--out", default="./experiment_data", help="Root output directory")
    parser.add_argument("--ratio", type=float, default=3.0, help="Non-PT sampling ratio (default: 3.0)")
    parser.add_argument("--workdir", default="/app", help="Remote working directory in container (default: /app)")
    
    args = parser.parse_args()
    
    # Assign to global variables
    CONTAINER_NAME = args.container_name
    PARSER_JAR_NAME = args.jar
    OUTPUT_DIR = args.out
    SAMPLE_RATIO = args.ratio
    REMOTE_WORKDIR = args.workdir

    print(f"🔥 Starting Auto Runner for: {CONTAINER_NAME}")
    print(f"   Parser: {PARSER_JAR_NAME}")
    print(f"   Output: {OUTPUT_DIR}/{CONTAINER_NAME}")

    # 0. Pre-check
    step0_check_tests_existence()

    # 1. Preparation
    step1_prepare_environment()
    
    # 2. Identification
    pts, nonpts = step2_run_parser_and_get_tests()
    print(f"📊 Found: {len(pts)} PTs, {len(nonpts)} Non-PTs")
    
    if not pts and not nonpts:
        print("❌ No tests found. Exiting.")
        sys.exit(0)

    # 3. Sampling
    target_count = int(len(pts) * SAMPLE_RATIO)
    if nonpts:
        selected_nonpts = random.sample(nonpts, min(len(nonpts), max(1, target_count)))
    else:
        selected_nonpts = []
        
    print(f"🎯 Plan: Run {len(pts)} PTs + {len(selected_nonpts)} Non-PTs")
        
    # 4. Execution
    if pts: step3_run_tests_loop(pts, "pt")
    if selected_nonpts: step3_run_tests_loop(selected_nonpts, "nonpt")
    
    print(f"\n🎉 Finished {CONTAINER_NAME}!")