import os
import csv
import argparse
import xml.etree.ElementTree as ET

def parse_jacoco_xml(xml_file):
    """
    Parses a JaCoCo XML file and returns a list of rows for the CSV.
    Rows contain coverage data at the method level.
    """
    rows = []
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Iterate through packages
        for package in root.findall('package'):
            package_name = package.get('name')
            
            # Iterate through classes
            for clazz in package.findall('class'):
                class_name = clazz.get('name')
                
                # Iterate through methods
                for method in clazz.findall('method'):
                    method_name = method.get('name')
                    desc = method.get('desc')
                    
                    # Initialize counters
                    inst_missed = 0
                    inst_covered = 0
                    line_missed = 0
                    line_covered = 0
                    
                    # Get counters
                    for counter in method.findall('counter'):
                        type_ = counter.get('type')
                        missed = int(counter.get('missed'))
                        covered = int(counter.get('covered'))
                        
                        if type_ == 'INSTRUCTION':
                            inst_missed = missed
                            inst_covered = covered
                        elif type_ == 'LINE':
                            line_missed = missed
                            line_covered = covered
                    
                    # Only add if there is some coverage or code (optional, but good for verification)
                    # If both covered are 0, it means the method wasn't executed at all (or empty)
                    # But we want to see what was covered, so we keep everything or filter?
                    # Let's keep everything that has instructions.
                    if inst_missed + inst_covered > 0:
                        rows.append({
                            'Package': package_name,
                            'Class': class_name,
                            'Method': method_name,
                            'Desc': desc,
                            'Inst_Missed': inst_missed,
                            'Inst_Covered': inst_covered,
                            'Line_Missed': line_missed,
                            'Line_Covered': line_covered
                        })
                        
    except ET.ParseError as e:
        print(f"❌ Error parsing {xml_file}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error processing {xml_file}: {e}")
        
    return rows

def process_project(project_name, input_root="experiment_data", output_root="coverage_csvs"):
    input_dir = os.path.join(input_root, project_name)
    output_dir = os.path.join(output_root, project_name)
    
    if not os.path.exists(input_dir):
        print(f"❌ Input directory not found: {input_dir}")
        return

    print(f"📂 Processing XMLs from: {input_dir}")
    print(f"💾 Saving CSVs to: {output_dir}")
    
    count = 0
    
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".xml"):
                xml_path = os.path.join(root, file)
                
                # Determine relative path to maintain structure (e.g. pt/test.xml -> pt/test.csv)
                rel_path = os.path.relpath(root, input_dir)
                target_dir = os.path.join(output_dir, rel_path)
                os.makedirs(target_dir, exist_ok=True)
                
                csv_filename = file.replace(".xml", ".csv")
                csv_path = os.path.join(target_dir, csv_filename)
                
                rows = parse_jacoco_xml(xml_path)
                
                if rows:
                    with open(csv_path, 'w', newline='') as f:
                        fieldnames = ['Package', 'Class', 'Method', 'Desc', 'Inst_Missed', 'Inst_Covered', 'Line_Missed', 'Line_Covered']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(rows)
                    # print(f"   ✅ Generated: {csv_filename}")
                else:
                    print(f"   ⚠️ No data found or empty XML: {file}")
                
                count += 1
                if count % 100 == 0:
                    print(f"   ... processed {count} files")

    print(f"🎉 Finished! Processed {count} XML files.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert JaCoCo XMLs to CSVs for verification")
    parser.add_argument("project_name", help="The project name (e.g., sag-commons-cli)")
    args = parser.parse_args()
    
    process_project(args.project_name)
